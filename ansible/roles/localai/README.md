# localai

LocalAI LLM server role.

## Description

This role sets up LocalAI for running large language models locally.

## Tasks

- Configures Docker environment
- Deploys LocalAI container(s)

## Requirements

- Docker installed
- Sufficient CPU/RAM (12 cores, 12GB+ recommended)
- GPU optional but recommended

## Variables

None

## Dependencies

- `base`
- `docker`

## Example Usage

```yaml
terraform:
  cpu_core_count: 12
  memory: 12288
  rootfs_size: 500G

ansible:
  roles:
    - base
    - docker
    - role: containers
      vars:
        containers:
          - name: openwebui
            state: up
          - name: litellm
            state: up
```

## Related Docker Stacks

- `openwebui` - Web interface for LLM interaction
- `litellm` - LLM API proxy

## Notes

LocalAI provides OpenAI-compatible API for locally-hosted models. Typically deployed with OpenWebUI for a ChatGPT-like interface.
