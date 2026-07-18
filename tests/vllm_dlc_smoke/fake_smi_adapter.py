import argparse
import json
import re


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-point", required=True)
    parser.add_argument("--server-pid", required=True, type=int)
    parser.add_argument("--process-group", required=True, type=int)
    parser.add_argument("--device-count", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    occupied = arguments.sample_point in {"after_ready", "during_request"}
    shared_match = re.search(
        r"shared-pids-d(\d+)-o(\d+)-p(\d+)", arguments.run_id
    )
    device_count = int(shared_match.group(1)) if shared_match else arguments.device_count
    occupied_device_count = int(shared_match.group(2)) if shared_match else device_count
    process_count = int(shared_match.group(3)) if shared_match else device_count
    shared_pids = [arguments.server_pid + index for index in range(process_count)]
    baseline_pids = [700001] if "baseline-occupied" in arguments.run_id else []
    cleanup_pids = (
        baseline_pids + [700002]
        if arguments.sample_point == "after_cleanup"
        and "cleanup-added-pid" in arguments.run_id
        else baseline_pids
    )
    print(
        json.dumps(
            {
                "adapter_schema": "vllm-dlc-smi-observation/v1",
                "devices": [
                    {
                        "device_key": (
                            "fixture-duplicate"
                            if "duplicate-devices" in arguments.run_id
                            else f"fixture-{index}"
                        ),
                        "health": "queryable_not_excluded",
                        "memory_total_mib": 63360,
                        "observed_pids": (
                            baseline_pids
                            + (
                                shared_pids
                                if shared_match and index < occupied_device_count
                                else [arguments.server_pid + index]
                            )
                            if occupied and index < occupied_device_count
                            else cleanup_pids
                        ),
                        "process_pids": (
                            shared_pids
                            if occupied and shared_match and index < occupied_device_count
                            else [arguments.server_pid + index]
                            if occupied and index < occupied_device_count
                            else []
                        ),
                    }
                    for index in range(device_count)
                ],
                "sample_point": arguments.sample_point,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
