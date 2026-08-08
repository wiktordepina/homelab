# service_catalogue

Service catalogue loader.

## Description

This role reads `config/services.yaml` and publishes it as the `catalogue` variable for the roles that follow it. It changes nothing on the target host.

The catalogue is the single source of truth for every name published under `homelab.matagoth.com`. Terraform reads the same file directly to create the DNS records; this role is how the file reaches Ansible.

## Tasks

- Loads `config/services.yaml` into the `catalogue` variable at play scope

## Requirements

- A rendered playbook run from the repository root, so that `playbook_dir` resolves to the repository (this is what the runner toolbox does)

## Variables

Sets `catalogue`, with two keys:

| Key | Description |
|-----|-------------|
| `catalogue.categories` | Ordered category list, each with an ordered `subcategories` list |
| `catalogue.services` | Service entries, each naming the category and subcategory it belongs to |

Refer to [`docs/reference/service-catalogue.md`](../../../docs/reference/service-catalogue.md) for the field-by-field schema.

## Dependencies

None. It must, however, be listed **before** any role that reads `catalogue`.

## Example Usage

```yaml
ansible:
  roles:
    - base
    - service_catalogue
    - nginx_reverse_proxy
    - certbot
```

## Notes

`include_vars` sets variables at play scope rather than role scope, which is the reason this works as a standalone role at all. The list in a container's `ansible.roles` is ordered; placing this role after a consumer leaves that consumer with an undefined `catalogue`.
