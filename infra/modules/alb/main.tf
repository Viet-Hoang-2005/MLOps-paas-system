# Target Group cho Worker Node
resource "aws_lb_target_group" "worker_tg" {
  name     = "mlops-worker-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  # Cấu hình health check trỏ vào Traefik Ping Endpoint
  health_check {
    path                = "/ping"
    protocol            = "HTTP"
    port                = "traffic-port"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }
}

# Gắn Target Group với Worker Node
resource "aws_lb_target_group_attachment" "worker_attach" {
  count            = length(var.worker_instance_ids)
  target_group_arn = aws_lb_target_group.worker_tg.arn
  target_id        = var.worker_instance_ids[count.index]
  port             = 80
}

# Load Balancer
resource "aws_lb" "api_alb" {
  name               = "mlops-api-lb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.lb_sg_id]
  subnets            = var.public_subnet_ids
  idle_timeout       = var.idle_timeout_seconds
}

# Listener HTTPS (Cổng 443)
resource "aws_lb_listener" "https_listener" {
  load_balancer_arn = aws_lb.api_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.worker_tg.arn
  }
}

# Listener HTTP (Cổng 80) - Tự động chuyển hướng sang HTTPS
resource "aws_lb_listener" "http_listener" {
  load_balancer_arn = aws_lb.api_alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
