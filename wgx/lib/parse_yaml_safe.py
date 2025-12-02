#!/usr/bin/env python3
import sys
import os
import shlex

# Try to use PyYAML, fall back to simpleyaml
try:
    import yaml
    def load_yaml(path):
        with open(path, 'r') as f:
            return yaml.safe_load(f)
except ImportError:
    # Add repo root to path to import lib.simpleyaml
    current_dir = os.path.dirname(os.path.abspath(__file__)) # wgx/lib
    repo_root = os.path.dirname(os.path.dirname(current_dir)) # root
    sys.path.insert(0, repo_root)
    from lib.simpleyaml import load as load_yaml

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
             # WGX use case: we don't really expect lists for task definitions
             # (tasks are commands). If we encounter a list, we might just skip or join?
             # For now, let's treat it as a space-separated string or ignore?
             # The existing awk parser ignores lists or breaks.
             pass
        else:
            items.append((new_key, v))
    return dict(items)

def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: parse_yaml_safe.py <yaml_file> <prefix>\n")
        sys.exit(1)

    yaml_file = sys.argv[1]
    prefix = sys.argv[2]

    try:
        path = os.path.abspath(yaml_file)
        # Check if file exists since simpleyaml expects Path
        from pathlib import Path
        data = load_yaml(Path(path))

        # Flatten and print
        flat_data = flatten_dict(data)

        for key, value in flat_data.items():
            # Sanitize key (alphanumeric + underscore)
            safe_key = "".join(c if c.isalnum() or c == '_' else '_' for c in key)
            final_key = f"{prefix}{safe_key}"

            # Sanitize value using shlex.quote to prevent code injection
            safe_value = shlex.quote(str(value))

            print(f"{final_key}={safe_value}")

    except Exception as e:
        sys.stderr.write(f"Error parsing YAML: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
