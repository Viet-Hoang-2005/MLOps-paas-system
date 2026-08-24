# Static inventory template for local development or manual override
# Copy this file to hosts.ini and replace the IPs accordingly.

[master]
master-node ansible_host=YOUR_MASTER_PUBLIC_IP private_ip=YOUR_MASTER_PRIVATE_IP

[workers]
worker-node-1 ansible_host=10.0.2.11 private_ip=10.0.2.11 ansible_ssh_common_args='-o ProxyJump=ubuntu@YOUR_MASTER_PUBLIC_IP -o StrictHostKeyChecking=accept-new'
worker-node-2 ansible_host=10.0.2.12 private_ip=10.0.2.12 ansible_ssh_common_args='-o ProxyJump=ubuntu@YOUR_MASTER_PUBLIC_IP -o StrictHostKeyChecking=accept-new'
