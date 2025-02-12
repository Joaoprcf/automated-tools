#!/usr/bin/env python3
import os
import subprocess
import requests
import argparse  # Added argparse to handle command line arguments


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Review Git diffs between the current branch state and a given commit or generate pull request descriptions."
    )
    # -b / --branch: Specify the commit to use as the base for the diff.
    # Default is set to "HEAD^1" (i.e., the commit before HEAD), so that the diff is computed between that commit and the current state (HEAD).
    parser.add_argument(
        "-b",
        "--branch",
        type=str,
        default="HEAD^1",
        help="Commit to diff against current branch state (default: HEAD^1)",
    )
    # -d / --description: If provided, generate a pull request description instead of a code review.
    parser.add_argument(
        "-d",
        "--description",
        action="store_true",
        help="Generate a short pull request description instead of a code review",
    )
    args = parser.parse_args()

    # Use the provided commit for diff; default to HEAD^1 if not specified.
    revision = args.branch
    generate_pr_desc = args.description

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
    # 1. Grab the diff between the specified commit and the current branch state (HEAD)
    ################################################################
    try:
        # Changed from "git show" to "git diff <revision> HEAD" to get the diff between the provided commit and the current state.
        commit_diff = subprocess.check_output(
            ["git", "diff", revision, "HEAD"], stderr=subprocess.STDOUT
        ).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        print(
            "Error retrieving git diff between",
            revision,
            "and HEAD:\n",
            e.output.decode(),
        )
        return

    ################################################################
    # 2. Get the list of changed files between the specified commit and HEAD
    ################################################################
    try:
        # Changed from "git diff-tree" to "git diff --name-only <revision> HEAD"
        changed_files_output = (
            subprocess.check_output(
                ["git", "diff", "--name-only", revision, "HEAD"],
                stderr=subprocess.STDOUT,
            )
            .decode("utf-8")
            .strip()
        )
        changed_files = changed_files_output.split("\n") if changed_files_output else []
    except subprocess.CalledProcessError as e:
        print(
            "Error retrieving changed files between",
            revision,
            "and HEAD:\n",
            e.output.decode(),
        )
        return

    ################################################################
    # 3. Construct the prompt message with the diff and file contents
    ################################################################
    review_prompt = []
    if generate_pr_desc:
        # If -d flag is provided, generate a pull request description
        review_prompt.append(
            "Please draft a concise, non-technical pull request description based on the following diff.\n"
            "The description should explain the purpose and impact of the changes in plain language.\n\n"
        )
    else:
        # Otherwise, perform a code review
        review_prompt.append(
            "Please provide a code review for the changes in this diff.\n"
            "Remember to also pay attention to the documentation and code consistency.\n"
            "I am not interested in what I have good, I am interested in fixing what I have wrong.\n\n"
            "If you have suggestions on how to fix issues with code examples, please include them.\n\n"
        )
    review_prompt.append("Below is the diff:\n\n")
    review_prompt.append(commit_diff.strip())
    review_prompt.append("\n\n---\n")

    # For each changed file, if it's smaller than 20kB, include its full content.
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
    print(f"Reviewing {len(changed_files)} files between {revision} and HEAD...\n")
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
