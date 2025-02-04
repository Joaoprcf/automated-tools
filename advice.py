#!/usr/bin/env python3
import argparse
import os
import subprocess
import requests
import sys
import time
import tempfile


def main():
    ################################################################
    # 0. Check API key or try sourcing /root/.openai_credentials
    ################################################################
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        try:
            # Attempt to load OPENAI_API_KEY via: source <(sudo cat /root/.openai_credentials)
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
            os.environ["OPENAI_API_KEY"] = openai_api_key
        except subprocess.CalledProcessError as e:
            print(
                "Failed to retrieve OPENAI_API_KEY from /root/.openai_credentials:\n",
                e.output.decode(),
            )
            sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set and could not be sourced. Exiting.")
        sys.exit(1)

    ################################################################
    # 1. Parse arguments
    ################################################################
    parser = argparse.ArgumentParser(
        description="Ask for changes in a file and rewrite it using OpenAI's o3-mini model."
    )
    # Changed the file argument from an optional flag (-f/--file) to a positional argument.
    # If not provided, the script will prompt the user.
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to the file you want to modify. If not specified, you'll be prompted.",
    )
    parser.add_argument(
        "-r",
        "--reasoning_effort",
        default="medium",
        help="Reasoning effort for the OpenAI model (e.g. low, medium, high). Default: medium",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path for the modified file. If not specified, the script uses <file>_modified<ext>.",
    )
    # New flag for interactive prompt editing.
    parser.add_argument(
        "-it",
        "--interactive",
        action="store_true",
        help="Open the generated prompt in VS Code for interactive editing before sending it.",
    )
    args = parser.parse_args()

    ################################################################
    # 2. If file is not provided, ask user
    ################################################################
    if not args.file:
        args.file = input("What file do you want to modify? ").strip()

    if not args.file or not os.path.isfile(args.file):
        print(f"Error: The provided file '{args.file}' does not exist.")
        sys.exit(1)

    ################################################################
    # 3. Read the entire file content
    ################################################################
    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        original_content = f.read()

    ################################################################
    # 4. Build the request prompt to the OpenAI API
    ################################################################
    # We want the entire updated file as response, so prompt accordingly:
    # e.g. "Here is the file content. Apply the requested changes and return
    # the entire updated file. Do not omit any part of it."
    changes = (
        ""
        if args.interactive
        else input(f"What changes do you want to make to {args.file}?\n").strip()
    )

    user_prompt = (
        "You are a coding assistant. I have the following file:\n\n"
        f"---\n{original_content}\n---\n\n"
        "Please return the entire updated file with the changes applied (include comments on those if possible), "
        "without omitting any part of the code. The result should be valid code only.\n"
        f"I want to apply these changes:\n{changes}\n\n"
    )

    ################################################################
    # 4a. If interactive mode is enabled, allow user to edit the prompt.
    ################################################################
    if args.interactive:
        # Create a temporary file with .txt extension.
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt", encoding="utf-8"
        ) as tmp_file:
            tmp_file.write(user_prompt)
            tmp_filepath = tmp_file.name

        print(
            f"\nInteractive mode enabled. Opening prompt file at {tmp_filepath} in VS Code...\n"
        )
        # Open the file with VS Code. Make sure 'code' is installed and in your PATH.
        try:
            subprocess.Popen(["code", tmp_filepath])
        except Exception as e:
            print(
                f"Failed to open VS Code. Ensure 'code' is installed and in your PATH. Error: {e}"
            )
            sys.exit(1)

        print("Waiting for you to modify the prompt file and save your changes...")
        # Read the original content that was written.
        original_prompt_content = user_prompt.strip()
        updated_prompt = original_prompt_content

        # Poll the file until its content changes (and is not empty).
        try:
            while updated_prompt == original_prompt_content or updated_prompt == "":
                time.sleep(1)
                with open(tmp_filepath, "r", encoding="utf-8") as f:
                    updated_prompt = f.read().strip()
        except KeyboardInterrupt:
            print("\nEditing interrupted by user. Exiting.")
            sys.exit(1)

        user_prompt = updated_prompt
        print("Detected updated prompt. Proceeding with the modified prompt.\n")
        # Optionally remove the temporary file.
        try:
            os.unlink(tmp_filepath)
        except Exception as e:
            print(f"Warning: Could not delete temporary file {tmp_filepath}: {e}")

    ################################################################
    # 5. Build the request to the OpenAI API
    ################################################################
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_api_key}",
    }

    payload = {
        "model": "o3-mini",  # The model you'd like to use
        "reasoning_effort": args.reasoning_effort,
        "messages": [
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    }

    ################################################################
    # 6. Send the request to OpenAI
    ################################################################
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180,  # longer timeout if needed
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as req_err:
        print(f"Request to OpenAI failed:\n{req_err}")
        sys.exit(1)

    response_json = response.json()
    if "choices" not in response_json or not response_json["choices"]:
        print("Error: Unexpected response from OpenAI:", response_json)
        sys.exit(1)

    modified_content = response_json["choices"][0]["message"]["content"]

    ################################################################
    # 7. Determine output filename
    ################################################################
    if args.output:
        out_file = args.output
    else:
        # Example: if the file is main.py -> main_modified.py
        base_name, ext = os.path.splitext(args.file)
        out_file = f"{base_name}_modified{ext}"

    ################################################################
    # 8. Write the modified file to disk
    ################################################################
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(modified_content)
    except OSError as e:
        print(f"Error: Could not write to {out_file} - {e}")
        sys.exit(1)

    ################################################################
    # 9. Print success message
    ################################################################
    print(f"Modified file saved to: {out_file}\n")
    print("=== Modified file content below ===\n")
    print(modified_content)


if __name__ == "__main__":
    main()
