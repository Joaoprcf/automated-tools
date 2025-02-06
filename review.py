#!/usr/bin/env python3

import os
import subprocess
import requests


def main():
    # If OPENAI_API_KEY is not set, try sourcing it from /root/.openai_credentials
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        try:
            # Here, we run a Bash shell that does:
            #   source <(sudo cat /root/.openai_credentials)
            # then echoes the variable, capturing it in Python
            openai_api_key = (
                subprocess.check_output(
                    [
                        "bash",
                        "-c",
                        "source <(sudo cat /root/.openai_credentials) && echo $OPENAI_API_KEY",
                    ],
                    stderr=subprocess.STDOUT,
                )
                .decode()
                .strip()
            )

            # Set it in the environment for this script’s lifetime
            os.environ["OPENAI_API_KEY"] = openai_api_key

        except subprocess.CalledProcessError as e:
            print(
                "Failed to retrieve OPENAI_API_KEY from /root/.openai_credentials:\n",
                e.output.decode(),
            )
            return

    # Sanity check if we *still* don't have it
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set and could not be sourced. Exiting.")
        return

    ################################################################
    # 1. Grab the last commit diff
    ################################################################
    try:
        commit_diff = subprocess.check_output(
            ["git", "show", "HEAD"], stderr=subprocess.STDOUT
        ).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        print("Error retrieving git diff for last commit:\n", e.output.decode())
        return

    ################################################################
    # 2. Get the list of changed files in the last commit
    ################################################################
    try:
        changed_files_output = (
            subprocess.check_output(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                stderr=subprocess.STDOUT,
            )
            .decode("utf-8")
            .strip()
        )
        changed_files = changed_files_output.split("\n") if changed_files_output else []
    except subprocess.CalledProcessError as e:
        print("Error retrieving changed files:\n", e.output.decode())
        return

    ################################################################
    # 3. Construct the prompt message with the diff
    ################################################################
    review_prompt = []
    review_prompt.append(
        "Please provide a code review for the changes in this last commit.\n"
        + "Remember to also pay attention to the documentation and code consistency.\n"
        + "I am not interested in what I have good, I am interested in fixing what I have wrong.\n\n"
    )
    review_prompt.append("Below is the diff:\n\n")
    review_prompt.append(commit_diff.strip())
    review_prompt.append("\n\n---\n")

    # For each changed file, if it's < 15kB, include its full content
    for cf in changed_files:
        cf = cf.strip()
        if cf and os.path.isfile(cf):
            file_size = os.path.getsize(cf)
            if file_size < 20000:
                with open(cf, "r", encoding="utf-8", errors="ignore") as f:
                    file_content = f.read()
                review_prompt.append(f"\n# File: {cf}\n")
                review_prompt.append(file_content)
                review_prompt.append("\n\n---\n")

    # Combine everything into a single string to send to the model
    review_message = "".join(review_prompt)

    ################################################################
    # 4. Prepare the request to the OpenAI API
    ################################################################
    openai_api_key = os.environ["OPENAI_API_KEY"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    payload = {
        "model": "o3-mini",  # The model you'd like to use
        "reasoning_effort": "high",
        "messages": [{"role": "user", "content": review_message}],
    }

    ################################################################
    # 5. Send the request and print the result
    ################################################################
    print(f"Reviewing {len(changed_files)} files in the last commit...\n")
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=150,
        )
        response.raise_for_status()
        response_json = response.json()

        # The response text is usually in response_json["choices"][0]["message"]["content"]
        content = response_json["choices"][0]["message"]["content"]
        print(content)
    except requests.exceptions.RequestException as req_err:
        print(f"Request failed:\n{req_err}")
    except KeyError:
        print("Unexpected response format:\n", response.text)


if __name__ == "__main__":
    main()
