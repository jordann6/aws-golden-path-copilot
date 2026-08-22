"""Render the architecture diagram with official AWS icons.

Generates docs/architecture.png. This is a build-time documentation tool, not a
runtime dependency, so `diagrams` is intentionally kept out of requirements.txt.

    pip install diagrams   # needs graphviz (`brew install graphviz`)
    python3 docs/architecture.py

The story the layout tells: Claude on Bedrock is advisory and sits OUTSIDE the
determinism boundary. Everything that actually decides (right-sizing, cost,
budget, policy) lives inside the "decisions in code" cluster, and the only
output is a reviewed pull request. Terraform applies solely on a human merge,
which is when the AWS resources on the right come into being.
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, EC2ImageBuilder
from diagrams.aws.database import RDS
from diagrams.aws.ml import Bedrock
from diagrams.aws.network import VPC
from diagrams.aws.security import SecretsManager
from diagrams.generic.blank import Blank
from diagrams.generic.network import Firewall
from diagrams.onprem.client import User
from diagrams.onprem.iac import Terraform
from diagrams.onprem.vcs import Github

graph_attr = {
    "fontsize": "16",
    "labelloc": "t",
    "pad": "0.4",
    "nodesep": "0.5",
    "ranksep": "0.9",
    # White canvas, not transparent: GitHub renders READMEs in both light and
    # dark themes, and the dark labels and the black GitHub glyph would vanish
    # on a transparent background in dark mode.
    "bgcolor": "white",
}

with Diagram(
    "Golden-Path FinOps Copilot",
    filename="docs/architecture",
    outformat="png",
    direction="LR",
    show=False,
    graph_attr=graph_attr,
):
    dev = User("Developer\nplain-language request")
    bedrock = Bedrock("Claude on Bedrock\ndrives tool loop · IAM/SigV4")

    with Cluster("Decisions in code (no LLM authority)"):
        right_size = Blank("right_size\ncheapest that fits")
        estimate = Blank("estimate_cost\nregion-aware · Infracost")
        budget = Blank("check_budget\nteam envelope")
        opa = Blank("OPA / Rego gate\ntags · GPU · budget · host posture")
        right_size >> Edge(color="darkgreen") >> estimate >> Edge(color="darkgreen") >> budget >> Edge(color="darkgreen") >> opa

    pr = Github("Pull Request\ntfvars · cost · rationale")
    terraform = Terraform("Terraform\napplies on human merge")

    with Cluster("Provisioned AWS (deploy-demo receipts)"):
        rds = RDS("RDS Postgres\nencrypted · private")
        secrets = SecretsManager("Secrets Manager\nmanaged password")
        vpc = VPC("VPC\nprivate subnets")
        ec2 = EC2("Hardened EC2\nIMDSv2 · no public IP")
        image_builder = EC2ImageBuilder("Image Builder\nCIS golden AMI")
        firewall = Firewall("Palo Alto VM-Series\negress inspection")

    dev >> bedrock >> Edge(label="tool use") >> right_size
    opa >> Edge(label="reviewed diff") >> pr >> Edge(label="human merge") >> terraform
    terraform >> Edge(color="darkorange") >> rds
    terraform >> Edge(color="darkorange") >> secrets
    terraform >> Edge(color="darkorange") >> vpc
    terraform >> Edge(color="darkorange") >> ec2
    image_builder >> Edge(label="golden AMI", style="dashed") >> ec2
    ec2 >> Edge(label="egress", color="darkred") >> firewall
