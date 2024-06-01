#!/usr/bin/python3
import threading
import queue
import random
import requests


def read_headers_from_file() -> list:
    """Read the 'headers.txt' file and return it as a list"""
    data = ""
    with open(file="headers.txt", mode="r", encoding="latin1") as file_handle:
        data = file_handle.read()

    return data.split(sep="\n")


def generate_cache_buster() -> str:
    """Generate a random string to confusing caches"""
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    length = 10
    string = "".join(random.choice(letters) for i in range(length))

    return string


def make_request(base_url: str, incoming_header: str) -> tuple[object, object]:
    """Send a request to a server with a given url and custom header
    Return the response (HTTPResponse obj) and exception if occurred
    """
    url = base_url + "?cachebuster=" + generate_cache_buster()

    parts = incoming_header.split(": ")
    if len(parts) != 2:
        return (None, None)

    headers = {parts[0]: parts[1]}

    exception = None
    try:
        response = requests.get(url=url, headers=headers, timeout=1)
    except Exception as exception:
        return (None, exception)

    return (response, exception)


def print_results(results):
    """Print the obtained results"""
    for result in results:
        print(
            f"[{result['status_code']}] [CL:{result['content_length']}] "
            f"[E:{result['exception']}] [{result['header']}]"
        )


def request_worker(results, q, base_url):
    """request_worker"""
    while True:
        header = q.get()
        print(f"Working on '{header}'")

        (response, exception) = make_request(base_url, header)
        if response is None and exception is None:
            continue

        result = {
            "header": header,
            "url": None,
            "exception": None,
            "status_code": None,
            "content_length": None,
        }

        if exception is not None:
            result["exception"] = f"{exception}"

        if response is not None:
            result["url"] = response.url
            result["status_code"] = response.status_code
            result["content_length"] = len(response.text)

        print(f"{result=}")
        results.append(result)

        q.task_done()


def main():
    """main()"""
    random.seed()

    base_url = "https://brokencrystals.com/"
    thread_count = 30

    headers = read_headers_from_file()
    q = queue.Queue()
    for header in headers:
        q.put(header)

    results = []

    for _ in range(thread_count):
        threading.Thread(target=request_worker, args=[results, q, base_url], daemon=True).start()

    q.join()

    return


if __name__ == "__main__":
    main()
