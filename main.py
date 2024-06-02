#!/usr/bin/python3
import threading
import queue
import random
import requests


def read_from_file(filename: str) -> list:
    """Read file and return it as a list"""
    lines = []
    with open(file=filename, mode="r", encoding="latin1") as file_handle:
        while True:
            line = file_handle.readline()
            if not line:
                break

            if line == "":
                continue

            if line.startswith("#"):
                continue

            line = line.replace("\n", "")
            lines.append(line)

    return lines


def generate_cache_buster() -> str:
    """Generate a random string to confusing caches"""
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    length = 10
    string = "".join(random.choice(letters) for i in range(length))

    return string


def make_request(
    base_url: str, incoming_header: str, user_agents: list
) -> tuple[object, object]:
    """Send a request to a server with a given url and custom header
    Return the response (HTTPResponse obj) and exception if occurred
    """
    url = base_url + "?cachebuster=" + generate_cache_buster()

    parts = incoming_header.split(": ")
    if len(parts) != 2:
        return (None, None)

    headers = {parts[0]: parts[1]}

    # Pick a random user agent - instead of the python-request
    user_agent = random.choice(user_agents)
    headers["User-Agent"] = user_agent

    exception = None
    try:
        response = requests.get(url=url, headers=headers, timeout=1)
    except Exception as exception:
        return (None, exception)

    return (response, exception)


def print_results(results):
    """Print the obtained results"""
    average_content_lengths = {}
    for result in results:
        if result["content_length"] is None:
            if "-1" not in average_content_lengths:
                average_content_lengths["-1"] = 0
            average_content_lengths["-1"] += 1

            continue

        if f'{result["content_length"]}' not in average_content_lengths:
            average_content_lengths[f'{result["content_length"]}'] = 0
        average_content_lengths[f'{result["content_length"]}'] += 1

    most_common_content_length = None
    for content_name, content_count in average_content_lengths.items():
        if most_common_content_length is None:
            most_common_content_length = {"name": content_name, "count": content_count}
            continue

        if most_common_content_length["count"] < content_count:
            most_common_content_length = {"name": content_name, "count": content_count}

    print(
        f"Most common Content-Length: {most_common_content_length['name']}, "
        f"hit count: {most_common_content_length['count']}"
    )
    print("Printing exceptions to the norm:")
    abnormal_count = 0
    for result in results:
        if (
            result["exception"] is None
            and result["status_code"] == 200
            and result["content_length"] == int(most_common_content_length["name"])
        ):
            continue

        abnormal_count += 1
        print(
            f"  [{result['status_code']}] [CL:{result['content_length']}] "
            f"[E:{result['exception']}] [{result['header']}]"
        )

    if abnormal_count == 0:
        print("  No abnormal responses found")


def request_worker(results, q, base_url, user_agents):
    """request_worker"""
    while True:
        try:
            header = q.get(timeout=1)
        except:
            break

        print(
            f"Working on '{header}' (left: {q.qsize()})                                    \r",
            end="",
        )

        (response, exception) = make_request(base_url, header, user_agents)
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

        # print(f"{result=}")
        results.append(result)

        q.task_done()


def main():
    """main()"""
    random.seed()

    base_url = "http://zero.webappsecurity.com/"
    thread_count = 30

    headers = read_from_file("headers.txt")
    user_agents = read_from_file("useragents.txt")
    # headers = headers[-2000:]
    headers.sort()
    q = queue.Queue()
    for header in headers:
        q.put(header)

    results = []

    for _ in range(thread_count):
        threading.Thread(
            target=request_worker, args=[results, q, base_url, user_agents], daemon=True
        ).start()

    q.join()

    print("\n======\nResults:")
    print_results(results)

    return


if __name__ == "__main__":
    main()
