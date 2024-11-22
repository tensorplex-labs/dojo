import argparse
import asyncio
import hashlib
import os
import random
import re
import string
from functools import partial

import minify_html
from bittensor.btlogging import logging as logger
from bs4 import BeautifulSoup
from jsmin import jsmin


# Obfuscator base class
class Obfuscator:
    @staticmethod
    def generate_random_string(length=8):
        return "".join(
            random.choices(string.ascii_letters, k=1)
            + random.choices(string.ascii_letters + string.digits, k=length - 1)
        )


class HTMLObfuscator(Obfuscator):
    @classmethod
    def obfuscate_html(cls, html_content):
        try:
            minify_params = {
                "do_not_minify_doctype": True,
                "ensure_spec_compliant_unquoted_attribute_values": True,
                "keep_comments": True,
                "keep_html_and_head_opening_tags": True,
                "keep_input_type_text_attr": True,
                "keep_spaces_between_attributes": True,
                "keep_ssi_comments": True,
                "preserve_brace_template_syntax": True,
                "preserve_chevron_percent_template_syntax": True,
                "remove_bangs": True,
                "remove_processing_instructions": True,
            }

            # Always include keep_closing_tags=True to avoid breaking the HTML structure
            selected_params = {"keep_closing_tags": True}
            random_params = random.sample(minify_params.items(), 5)
            selected_params.update(random_params)

            # Use minify to obfuscate the JavaScript code
            minified_content = minify_html.minify(
                html_content,
                **selected_params,
            )

            # Apply a random number of obfuscation techniques
            obfuscated_content = cls.apply_techniques(minified_content)

            # Optionally add random comments (50% chance)
            if random.random() < 0.5:
                obfuscated_content = cls.add_enclosing_comments(obfuscated_content)

            return obfuscated_content
        except Exception as e:
            logger.error(f"Obfuscation failed for HTML: {str(e)}")
            return html_content

    @classmethod
    def apply_techniques(cls, content):
        techniques = [
            cls.add_random_attributes,
            cls.add_dummy_elements,
            cls.shuffle_attributes,
        ]
        num_techniques = random.randint(1, len(techniques))
        chosen_techniques = random.sample(techniques, num_techniques)

        soup = BeautifulSoup(content, "html.parser")
        for technique in chosen_techniques:
            soup = technique(soup)
        return str(soup)

    @classmethod
    def add_enclosing_comments(cls, content):
        return (
            f"<!-- {cls.generate_random_string(16)} -->\n"
            f"{content}\n"
            f"<!-- {cls.generate_random_string(16)} -->"
        )

    @classmethod
    def add_random_attributes(cls, soup):
        for tag in soup.find_all():
            if random.random() < 0.3:
                tag[cls.generate_random_string(5)] = cls.generate_random_string(8)
        return soup

    @classmethod
    def add_dummy_elements(cls, soup):
        dummy_elements = [
            soup.new_tag(
                "div", style="display:none;", string=cls.generate_random_string(20)
            )
            for _ in range(random.randint(1, 5))
        ]
        soup.body.extend(dummy_elements)
        return soup

    @staticmethod
    def shuffle_attributes(soup):
        for tag in soup.find_all():
            tag.attrs = dict(random.sample(list(tag.attrs.items()), len(tag.attrs)))
        return soup


# Todo: Test further JS obfuscation techniques and enable it
class JSObfuscator(Obfuscator):
    @staticmethod
    def simple_minify(js_code):
        return jsmin(js_code)

    @classmethod
    def obfuscate_javascript(cls, html_content: str) -> str:
        """Find and obfuscate all JavaScript content using BeautifulSoup."""
        soup = BeautifulSoup(html_content, "html.parser")

        # Find and obfuscate <script> tags
        for script in soup.find_all("script"):
            if script.string:  # Only process if there's content
                script.string = cls.apply_js_obfuscation(script.string)

        # Find and obfuscate inline event handlers
        for tag in soup.find_all():
            for attr in list(tag.attrs):
                if attr.startswith("on"):  # onclick, onload, etc.
                    tag[attr] = cls.apply_js_obfuscation(tag[attr])

        return str(soup)

    @classmethod
    def apply_js_obfuscation(cls, js_code: str) -> str:
        """Apply multiple JavaScript obfuscation techniques."""
        techniques = [
            # cls.add_string_encoding,
            cls.add_dead_code,
            # cls.add_control_flow_obfuscation,
            # cls.add_self_defending_code,
        ]

        obfuscated_code = js_code
        # Apply 2-3 random techniques
        for technique in random.sample(techniques, 1):  # random.randint(2, 3)
            obfuscated_code = technique(obfuscated_code)
        return obfuscated_code

    @classmethod
    def add_string_encoding(cls, js_code: str) -> str:
        """Safely encode string literals using hex encoding."""
        # Only match simple string literals, avoiding template literals and regex
        string_pattern = re.compile(r'(["\']).+?\1')

        def encode_string(match):
            # Get the string without quotes
            full_str = match.group(0)
            content = full_str[1:-1]

            # Skip if string is empty or already looks encoded
            if not content or "\\" in content:
                return full_str

            # Skip strings that look like HTML IDs, classes, or event names
            if any(skip in content.lower() for skip in ["#", ".", "on"]):
                return full_str

            # 30% chance to encode each string
            if random.random() > 0.3:
                return full_str

            # Use simple hex encoding which is reliable
            hex_array = []
            for char in content:
                hex_array.append(hex(ord(char)))

            # Create a string from hex values
            return f"String.fromCharCode({','.join(hex_array)})"

        return string_pattern.sub(encode_string, js_code)

    @classmethod
    def add_dead_code(cls, js_code: str) -> str:
        """Add harmless dead code that will be optimized out."""
        # Dead code that's safe to insert and will be optimized away
        dead_code_samples = [
            # "if (false) { console.log('unreachable'); }",
            "while (false) { break; }",
            # "try { if (0) throw 0; } catch(e) {}",
            # f"var _{cls.generate_random_string(5)} = function() {{ return false; }}();",
            # "switch (false) { case true: break; default: break; }",
            # "for (var i = 0; i < 0; i++) { console.log(i); }",
        ]

        # Split code into statements using semicolons
        statements = js_code.split(";")

        # Only insert after complete statements
        for _ in range(random.randint(1, 2)):
            if len(statements) > 1:  # Only if we have multiple statements
                # Choose a position between statements
                position = random.randint(1, len(statements) - 1)
                dead_code = random.choice(dead_code_samples)
                statements.insert(position, dead_code)

        # Rejoin with semicolons
        return ";".join(statements)

    @classmethod
    def add_control_flow_obfuscation(cls, js_code: str) -> str:
        """Add control flow obfuscation using switch-case or conditional statements."""
        # Wrap the entire code in a self-executing function with control flow logic
        switch_var = cls.generate_random_string(5)
        wrapped_code = f"""
                        (function() {{
                            var {switch_var} = {random.randint(1, 100)};
                            switch({switch_var} % 3) {{
                                case 0:
                                    if ({switch_var} % 2) {{
                                        {js_code}
                                    }} else {{
                                        {js_code}
                                    }}
                                    break;
                                case 1:
                                    while({switch_var}-- > {switch_var}-1) {{
                                        {js_code}
                                        break;
                                    }}
                                    break;
                                default:
                                    {js_code}
                            }}
                        }})();
                        """
        return wrapped_code

    @classmethod
    def add_self_defending_code(cls, js_code: str) -> str:
        """Add code that makes debugging and analysis more difficult."""
        random_key = cls.generate_random_string(8)
        protected_code = f"""
                        (function() {{
                            var {random_key} = new Date().getTime();
                            if (new Date().getTime() - {random_key} > 100) {{
                                return;
                            }}
                            {js_code}
                        }})();
                        """
        return protected_code


async def obfuscate_html_and_js(html_content, timeout=30):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                None, partial(_obfuscate_html_and_js_sync, html_content)
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error(f"Obfuscation timed out after {timeout} seconds")
        return html_content  # Return original content if obfuscation times out


def _obfuscate_html_and_js_sync(content):
    try:
        obfuscated_html = HTMLObfuscator.obfuscate_html(content)
        return obfuscated_html
    except Exception as e:
        logger.error(f"Minification failed: {str(e)}")
        logger.warning("Falling back to simple minification.")
        return JSObfuscator.simple_minify(content)


async def process_file(input_file: str, output_file: str):
    try:
        with open(input_file, encoding="utf-8") as file:
            original_content = file.read()
    except FileNotFoundError:
        logger.error(f"Error: The file '{input_file}' was not found.")
        return
    except OSError:
        logger.error(f"Error: Could not read the file '{input_file}'.")
        return

    obfuscated = await obfuscate_html_and_js(original_content)

    try:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(obfuscated)
        logger.info(f"Obfuscated content has been written to '{output_file}'")

        # Calculate and display hashes to show difference
        original_hash = hashlib.md5(original_content.encode()).hexdigest()
        obfuscated_hash = hashlib.md5(obfuscated.encode()).hexdigest()
        logger.info(f"\nOriginal content MD5: {original_hash}")
        logger.info(f"Obfuscated content MD5: {obfuscated_hash}")
    except OSError:
        logger.error(f"Error: Could not write to the file '{output_file}'.")


# Function to test the obfuscation
# Command to run: python obfuscation_utils.py input.html
async def main():
    parser = argparse.ArgumentParser(
        description="Obfuscate HTML and JavaScript content"
    )
    parser.add_argument("input_file", help="Path to the input HTML file")
    parser.add_argument(
        "-o", "--output", help="Path to the output obfuscated HTML file (optional)"
    )
    args = parser.parse_args()

    # Generate default output filename based on input filename
    input_filename = os.path.basename(args.input_file)
    input_name, input_ext = os.path.splitext(input_filename)
    output_file = args.output or f"{input_name}_obfuscated{input_ext}"

    await process_file(args.input_file, output_file)


if __name__ == "__main__":
    asyncio.run(main())
