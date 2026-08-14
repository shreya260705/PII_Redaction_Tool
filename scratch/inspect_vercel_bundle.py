import requests
import re

def main():
    url = "https://pii-redaction-tool-c777.vercel.app"
    print(f"Fetching Vercel app HTML from: {url}")
    html = requests.get(url).text

    # Extract JS script files
    js_files = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
    print(f"Found JS script links: {js_files}")

    for js_path in js_files:
        if js_path.startswith('/'):
            js_url = url + js_path
        else:
            js_url = js_path

        print(f"\n--- Analyzing JS Bundle: {js_url} ---")
        js_content = requests.get(js_url).text
        print(f"Bundle size: {len(js_content)} bytes")

        # Check endpoints present in the compiled JS bundle
        has_async = "/api/redact-async" in js_content
        has_sync = "/api/redact" in js_content
        has_tasks = "/api/tasks" in js_content

        print(f"  Contains '/api/redact-async': {has_async}")
        print(f"  Contains '/api/redact':       {has_sync}")
        print(f"  Contains '/api/tasks':        {has_tasks}")

        # Find backend URL references
        render_urls = set(re.findall(r'https?://[^\s"\'\`]+onrender\.com[^\s"\'\`]*', js_content))
        print(f"  Render backend URLs found: {render_urls}")

        # Search for exact endpoint calls in JS bundle
        endpoint_snippets = re.findall(r'["\'](/api/[^"\']+)["\']', js_content)
        print(f"  API endpoints found in bundle: {set(endpoint_snippets)}")

        # Print code snippet around /api/
        for match in re.finditer(r'/api/[a-zA-Z0-9_-]+', js_content):
            start = max(0, match.start() - 100)
            end = min(len(js_content), match.end() + 100)
            print(f"\n  [Snippet around match]:\n{js_content[start:end]}")

if __name__ == "__main__":
    main()
