"""CLI entry point for the internal link audit engine."""

import click


@click.command()
@click.option("--client", required=True, help="Client slug matching a folder under clients/")
@click.option("--auditor", default=None, help="Run only this auditor (e.g. universal_nav)")
@click.option("--classify-only", is_flag=True, help="Classify URLs only; skip auditors")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
def main(client: str, auditor: str | None, classify_only: bool, verbose: bool) -> None:
    """Run the internal linking audit for a client."""
    print("not implemented")


if __name__ == "__main__":
    main()
