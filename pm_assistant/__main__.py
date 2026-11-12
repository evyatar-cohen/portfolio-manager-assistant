"""CLI entry point. The --pm flag stands in for the identity the WebAPI would pass from SSO/JWT."""
import argparse

from pm_assistant.agent import answer


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pm_assistant")
    parser.add_argument("--customer", required=True, help="customer ID, e.g. C-1042")
    parser.add_argument("--pm", default="PM-001", help="requesting portfolio manager ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="show status, tool calls and violations")
    parser.add_argument("question")
    args = parser.parse_args()

    result = answer(args.pm, args.customer, args.question)
    if args.verbose:
        print(f"[status={result.status} tools={result.tool_calls} violations={result.violations}]")
    print(result.text)


if __name__ == "__main__":
    main()
