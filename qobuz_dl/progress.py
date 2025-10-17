"""
Provides pre-configured Rich progress bars for different download scenarios.
"""

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TaskProgressColumn,
)


def get_rich_bytes_progress():
    """
    Returns a Rich Progress instance configured for tracking downloads in bytes.
    Includes transfer speed and total size.
    """
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        TimeRemainingColumn(),
        transient=True,  # Clears the progress bar on completion.
    )


def get_rich_files_progress():
    """
    Returns a Rich Progress instance configured for tracking progress by file count.
    Useful when total download size is not known in advance.
    """
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),  # Shows "X/Y files".
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        TimeRemainingColumn(),
        transient=True,
    )
