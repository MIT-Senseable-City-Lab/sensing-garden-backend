# =============================================================================
# Route 53 DNS for sensinggarden.com
# =============================================================================

resource "aws_route53_zone" "main" {
  name = "sensinggarden.com"
}

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.sensinggarden.com"
  type    = "CNAME"
  ttl     = 300
  records = ["d-6qtiy9wz70.execute-api.us-east-1.amazonaws.com"]
}

resource "aws_route53_record" "dashboard_apex" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "sensinggarden.com"
  type    = "A"

  alias {
    name                   = aws_elastic_beanstalk_environment.web.cname
    zone_id                = "Z117KPS5GTRQ2G"
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "dashboard_www" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "www.sensinggarden.com"
  type    = "CNAME"
  ttl     = 300
  records = ["sensinggarden.com"]
}

output "nameservers" {
  value       = aws_route53_zone.main.name_servers
  description = "Set these as custom nameservers at your domain registrar (Namecheap)"
}
