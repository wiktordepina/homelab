variable "dns_ip" {
  type    = string
  default = "10.20.1.201"
}

variable "tsig_key" {
  type      = string
  sensitive = true
}
