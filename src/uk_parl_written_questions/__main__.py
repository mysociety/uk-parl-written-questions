import rich_click as click

from .fetch import create_dataset, get_all_data


@click.group()
def cli():
    pass


def main():
    cli()


@cli.command()
def fetch():
    get_all_data(force_recent=True)


@cli.command()
def create():
    create_dataset()


if __name__ == "__main__":
    main()
