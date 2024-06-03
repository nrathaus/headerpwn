#!/usr/bin/python3
import sys
import threading
import queue
import random
import json
import argparse
import time
import shlex

import requests

VERSION = "1.6.3"


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
    base_url: str,
    incoming_header: str,
    user_agents: list,
    max_retry: int,
    retry_delay: int,
) -> tuple[object, object, object]:
    """Send a request to a server with a given url and custom header
    Return the response (HTTPResponse obj) and exception if occurred
    """
    url = base_url + "?cachebuster=" + generate_cache_buster()

    parts = incoming_header.split(": ")
    if len(parts) != 2:
        return (None, None, None)

    headers = {parts[0]: parts[1]}

    retry = 0
    prepped = None
    response = None
    request = None
    while True:
        # Pick a random user agent - instead of the python-request
        #  we put it here, so that retry will attempt a different user
        #  agent - we aren't trying to test for (diff) user agents here..
        user_agent = random.choice(user_agents)
        headers["User-Agent"] = user_agent

        request = requests.Request(method="get", url=url, headers=headers)
        prepped = request.prepare()
        session = requests.Session()
        try:
            response = session.send(prepped, timeout=1)

            # If no exception occurred, break
            break
        except Exception as exception:
            # Exception occurred, retry
            retry += 1
            if retry > max_retry:
                return (prepped, None, exception)

            time.sleep(retry_delay / 1000)  # Convert to ms

    return (prepped, response, None)


def to_curl(request, compressed=False, verify=True):
    """
    Taken from: https://github.com/ofw/curlify/blob/master/curlify.py
        (seems like an unmaintained project)
    Returns string with curl command by provided request object

    Parameters
    ----------
    compressed : bool
        If `True` then `--compressed` argument will be added to result
    """
    parts = [
        ("curl", None),
        ("-X", request.method),
    ]

    for k, v in sorted(request.headers.items()):
        parts += [("-H", "{0}: {1}".format(k, v))]

    if request.body:
        body = request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parts += [("-d", body)]

    if compressed:
        parts += [("--compressed", None)]

    if not verify:
        parts += [("--insecure", None)]

    parts += [(None, request.url)]

    flat_parts = []
    for k, v in parts:
        if k:
            flat_parts.append(shlex.quote(k))
        if v:
            flat_parts.append(shlex.quote(v))

    return " ".join(flat_parts)


def print_results(json_output: bool, output_results: bool, results: list) -> None:
    """Print the obtained results"""
    average_content_lengths = {}
    for result in results:
        if result["content_length"] is None:
            if "-1" not in average_content_lengths:
                average_content_lengths["-1-None"] = 0

            average_content_lengths["-1-None"] += 1

            continue

        if (
            f'{result["content_length"]}-{result["status_code"]}'
            not in average_content_lengths
        ):
            average_content_lengths[
                f'{result["content_length"]}-{result["status_code"]}'
            ] = 0

        average_content_lengths[
            f'{result["content_length"]}-{result["status_code"]}'
        ] += 1

    most_common_content_length = None
    for content_name, content_count in average_content_lengths.items():
        content_length = ""
        status_code = ""
        if content_name.startswith("-1"):
            content_length = -1
            status_code = int(content_name[len("-1") :])
        else:
            (content_length, status_code) = content_name.split("-")
            status_code = int(status_code)

        if most_common_content_length is None or (
            most_common_content_length is not None
            and most_common_content_length["count"] < content_count
        ):
            most_common_content_length = {
                "name": content_length,
                "count": content_count,
                "status_code": status_code,
            }

    json_obj = {
        "average_content_lengths": average_content_lengths,
        "most_common_content_length": most_common_content_length,
        "abnormalities": [],
    }
    if output_results:
        json_obj["results"] = results

    if not json_output:
        print(
            f"Most common Content-Length: {most_common_content_length['name']}, "
            f"hit count: {most_common_content_length['count']}"
        )
        print("Printing exceptions to the norm:")

    abnormal_count = 0
    for result in results:
        abnormal = False
        if result["exception"] is not None:
            abnormal = True

        if result["status_code"] != most_common_content_length["status_code"] or result[
            "content_length"
        ] != int(most_common_content_length["name"]):
            abnormal = True

        if not abnormal:
            continue

        json_obj["abnormalities"].append(result)
        abnormal_count += 1

        if not json_output:
            print(
                f"  [{result['status_code']}] [CL:{result['content_length']}] "
                f"[E:{result['exception']}] [{result['header']}]"
            )

    json_obj["abnormal_count"] = abnormal_count

    if not json_output:
        if abnormal_count == 0:
            print("  No abnormal responses found")
        else:
            print(f"  {abnormal_count} abnormal responses")
    else:
        print(json.dumps(json_obj, indent=1))


def request_worker(**kwargs) -> None:  # results, q, base_url, user_agents
    """request_worker"""
    while True:
        try:
            header = kwargs["q"].get(timeout=1)
        except:
            break

        q = kwargs["q"]
        if kwargs["json_status"]:
            json_obj = {
                "status": f"Testing '{header}'",
                "left": q.qsize(),
                "progress": f"{(1 - q.qsize() / kwargs['total']) * 100.0:0.2f}",
            }
            print(json.dumps(json_obj))
        else:
            print(
                f"Testing '{header}' ({q.qsize()} of {kwargs['total']})"
                "                                                \r",
                end="",
            )

        (request, response, exception) = make_request(
            kwargs["base_url"],
            header,
            kwargs["user_agents"],
            kwargs["max_retry"],
            kwargs["retry_delay"],
        )
        if response is None and exception is None:
            continue

        result = {
            "header": header,
            "url": None,
            "exception": None,
            "status_code": None,
            "content_length": None,
            "curl": to_curl(request),
        }

        if exception is not None:
            result["exception"] = f"{exception}"

        if response is not None:
            result["url"] = response.url
            result["status_code"] = response.status_code
            result["content_length"] = len(response.text)
            result["user_agent"] = response.request.headers["User-Agent"]

        kwargs["results"].append(result)

        q.task_done()


def main():
    """main()"""

    # Some part are randomly picked, so seed it
    random.seed()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base_url",
        help="URL to analyze (include http/https prefix and port if relevant)",
        type=str,
    )
    parser.add_argument(
        "--thread_count",
        help="Maximum amount of threads to run (positive int, min 1)",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--max_retry",
        help=(
            "Maximum amount of retries that 'requests' will attempt "
            "(positive int, min 0 - disabled, max 60)"
        ),
        type=int,
        default=5,
    )
    parser.add_argument(
        "--retry_delay",
        help=(
            "Delay in ms between requests when a 'requests' fails "
            "(positive int, min 1ms, max 1000ms)"
        ),
        type=int,
        default=100,
    )
    parser.add_argument(
        "--output_results",
        help="Output all the HTTP responses (normal and abnormal)",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--json_output",
        help="Output the results in JSON format",
        default=True,
        action="store_true",
    )
    parser.add_argument(
        "--json_status",
        help="Output the status in JSON format",
        default=False,
        action="store_true",
    )
    args = parser.parse_args()

    base_url = None
    if args.base_url:
        base_url = args.base_url

    if args.retry_delay < 1 or args.retry_delay > 1000:
        args.retry_delay = 100

    if args.max_retry < 0 or args.max_retry > 60:
        args.max_retry = 5

    if args.thread_count < 1:
        args.thread_count = 1

    if base_url is None:
        parser.print_help()
        sys.exit()

    thread_count = args.thread_count

    headers = read_from_file("headers.txt")
    user_agents = read_from_file("useragents.txt")

    # Sort the headers to make it easier to replicate
    headers.sort()

    q = queue.Queue()
    for header in headers:
        q.put(header)

    results = []

    for _ in range(thread_count):
        threading.Thread(
            target=request_worker,
            kwargs={
                "results": results,
                "q": q,
                "base_url": base_url,
                "user_agents": user_agents,
                "json_status": args.json_status,
                "total": q.qsize(),
                "max_retry": args.max_retry,
                "retry_delay": args.retry_delay,
            },
            daemon=True,
        ).start()

    q.join()

    if not args.json_output:
        print("\n======\nResults:")
    print_results(args.json_output, args.output_results, results)

    return


if __name__ == "__main__":
    main()
