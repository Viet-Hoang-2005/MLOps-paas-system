#!/usr/bin/env python3
"""Build an Ansible inventory from the repository Terraform outputs."""
import json
import os
import subprocess
import sys


REQUIRED_OUTPUTS = (
    "master_public_ip",
    "master_private_ip",
    "worker_private_ips",
    "vpc_id",
    "ec2_key_pair_name",
)

def fail(message):
    sys.stderr.write(f"Ansible inventory error: {message}\n")
    raise SystemExit(1)


def output_value(outputs, name):
    value = outputs.get(name, {}).get("value")
    if value in (None, "", []):
        fail(
            f"Terraform output '{name}' is missing. Run terraform apply with "
            "enable_network=true and enable_k3s_compute=true before Ansible."
        )
    return value


def get_tf_output():
    # infra directory is ../../infra relative to this file
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    infra_dir = os.path.join(base_dir, 'infra')
    try:
        out = subprocess.check_output(
            ["terraform", "output", "-json"], cwd=infra_dir, stderr=subprocess.PIPE
        )
        return json.loads(out)
    except FileNotFoundError:
        fail("terraform is not installed or is not available on PATH.")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        fail(f"terraform output failed: {detail or exc}")
    except json.JSONDecodeError as exc:
        fail(f"terraform output returned invalid JSON: {exc}")

def main():
    tf_data = get_tf_output()

    for output_name in REQUIRED_OUTPUTS:
        output_value(tf_data, output_name)

    master_ip = output_value(tf_data, "master_public_ip")
    master_private_ip = output_value(tf_data, "master_private_ip")
    worker_ips = output_value(tf_data, "worker_private_ips")
    vpc_id = output_value(tf_data, "vpc_id")
    ec2_key_pair_name = output_value(tf_data, "ec2_key_pair_name")
    if not isinstance(worker_ips, list):
        fail("Terraform output 'worker_private_ips' must be a list.")
    if len(worker_ips) != 2:
        fail(
            "Terraform output 'worker_private_ips' must contain exactly two "
            f"static workers; received {len(worker_ips)}."
        )
    karpenter_node_instance_profile = tf_data.get('karpenter_node_instance_profile_name', {}).get('value')
    karpenter_interruption_queue = tf_data.get('karpenter_interruption_queue_name', {}).get('value')
    karpenter_controller_policy = tf_data.get('karpenter_controller_policy_arn', {}).get('value')
    karpenter_k3s_api_hostname = tf_data.get('karpenter_k3s_api_hostname', {}).get('value')
    karpenter_k3s_api_endpoint = tf_data.get('karpenter_k3s_api_endpoint', {}).get('value')
    karpenter_k3s_token_secret_arn = tf_data.get('karpenter_k3s_token_secret_arn', {}).get('value')
    alb_target_group_arn = tf_data.get("alb_target_group_arn", {}).get("value")

    inventory = {
        "_meta": {
            "hostvars": {}
        },
        "all": {
            "children": ["master", "workers"],
            "vars": {
                "terraform_vpc_id": vpc_id,
                "terraform_ec2_key_pair_name": ec2_key_pair_name,
                "terraform_alb_target_group_arn": alb_target_group_arn or "",
            },
        },
        "master": {
            "hosts": []
        },
        "workers": {
            "hosts": []
        }
    }

    if master_ip:
        master_host = "master-node"
        inventory["master"]["hosts"].append(master_host)
        inventory["_meta"]["hostvars"][master_host] = {
            "ansible_host": master_ip,
            "private_ip": master_private_ip,
            "k3s_node_name": master_host,
            "terraform_karpenter_node_instance_profile_name": karpenter_node_instance_profile or "",
            "terraform_karpenter_interruption_queue_name": karpenter_interruption_queue or "",
            "terraform_karpenter_controller_policy_arn": karpenter_controller_policy or "",
            "terraform_karpenter_k3s_api_hostname": karpenter_k3s_api_hostname or "",
            "terraform_karpenter_k3s_api_endpoint": karpenter_k3s_api_endpoint or "",
            "terraform_karpenter_k3s_token_secret_arn": karpenter_k3s_token_secret_arn or "",
        }
        if karpenter_node_instance_profile:
            inventory["_meta"]["hostvars"][master_host]["karpenter_node_instance_profile_name"] = karpenter_node_instance_profile
        if karpenter_interruption_queue:
            inventory["_meta"]["hostvars"][master_host]["karpenter_interruption_queue_name"] = karpenter_interruption_queue

    if worker_ips and isinstance(worker_ips, list):
        for idx, w_ip in enumerate(worker_ips):
            worker_host = f"worker-node-{idx+1}"
            inventory["workers"]["hosts"].append(worker_host)
            host_vars = {
                "ansible_host": w_ip,
                "private_ip": w_ip,
                "k3s_node_name": worker_host,
            }
            if master_ip:
                host_vars["ansible_ssh_common_args"] = (
                    "-o ProxyCommand=\"ssh -i ~/.ssh/aws_key "
                    "-o IdentitiesOnly=yes "
                    "-o StrictHostKeyChecking=accept-new "
                    f"-W %h:%p ubuntu@{master_ip}\" "
                    "-o StrictHostKeyChecking=accept-new"
                )
            inventory["_meta"]["hostvars"][worker_host] = host_vars

    # Output inventory in JSON format
    print(json.dumps(inventory, indent=2))

if __name__ == "__main__":
    main()
