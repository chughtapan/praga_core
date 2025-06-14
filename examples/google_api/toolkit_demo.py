from datetime import datetime, timedelta

from calendar_toolkit import CalendarToolkit  # noqa: F401
from gmail_toolkit import GmailToolkit  # noqa: F401


def demo_gmail_toolkit():
    """Demonstrate Gmail toolkit functionality."""
    print("=" * 60)
    print("Gmail Toolkit Demo")
    print("=" * 60)

    try:
        print("Initializing Gmail toolkit...")
        gmail = GmailToolkit()

        # Demo 1: Direct method calls (no pagination)
        print("\n1. Direct Method Calls (No Pagination)")
        print("-" * 40)
        print("Getting recent emails using direct method call...")
        recent_emails = gmail.get_recent_emails(days=7)
        print(f"Found {len(recent_emails)} recent emails")

        # Show first few emails
        for i, email in enumerate(recent_emails[:2]):
            print(f"\nRecent Email {i+1}:")
            print(f"  Subject: {email.subject}")
            print(f"  From: {email.sender}")
            print(f"  Date: {email.time}")

        # Demo 2: Invoke method calls (with pagination)
        print("\n2. Invoke Method Calls (With Pagination)")
        print("-" * 40)
        print("Getting emails with keyword using invoke method (paginated)...")

        # Use invoke_tool for paginated results
        paginated_result = gmail.invoke_tool(
            "get_emails_with_body_keyword", {"keyword": "meeting", "max_results": 20}
        )

        print("Page 0 results:")
        print(f"  Documents in this page: {len(paginated_result['documents'])}")
        print(f"  Has next page: {paginated_result.get('has_next_page', 'N/A')}")
        print(f"  Total documents: {paginated_result.get('total_documents', 'N/A')}")

        # Show first email from paginated results
        if paginated_result["documents"]:
            first_email = paginated_result["documents"][0]
            print("\nFirst paginated email:")
            print(f"  Subject: {first_email.get('subject', 'N/A')}")
            print(f"  From: {first_email.get('sender', 'N/A')}")

        # Demo 3: String input for invoke
        print("\n3. String Input for Invoke")
        print("-" * 40)
        string_result = gmail.invoke_tool("get_emails_with_body_keyword", "project")
        print(f"String input result - documents: {len(string_result['documents'])}")

        # Demo 4: Compare direct vs invoke for same tool
        print("\n4. Comparing Direct vs Invoke Calls")
        print("-" * 40)

        # Direct call
        print("Direct call to get_emails_by_sender...")
        direct_emails = gmail.get_emails_by_sender("test@example.com", max_results=10)
        print(f"Direct call returned {len(direct_emails)} emails")

        # Invoke call
        print("Invoke call to get_emails_by_sender...")
        invoke_emails = gmail.invoke_tool(
            "get_emails_by_sender",
            {"sender_email": "test@example.com", "max_results": 10},
        )
        print(
            f"Invoke call returned {len(invoke_emails['documents'])} emails in current page"
        )
        if "total_documents" in invoke_emails:
            print(f"Total documents available: {invoke_emails['total_documents']}")

        # Demo 5: Tool inspection
        print("\n5. Tool Inspection")
        print("-" * 40)
        print("Available tools in Gmail toolkit:")
        for tool_name in gmail.tools.keys():
            tool = gmail.get_tool(tool_name)
            print(f"  - {tool.name}: {tool.description[:60]}...")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please set up OAuth credentials first!")
    except Exception as e:
        print(f"Error accessing Gmail: {e}")


def demo_calendar_toolkit():
    """Demonstrate Calendar toolkit functionality."""
    print("\n" + "=" * 60)
    print("Calendar Toolkit Demo")
    print("=" * 60)

    try:
        print("Initializing Calendar toolkit...")
        calendar = CalendarToolkit()

        # Demo 1: Direct method calls
        print("\n1. Direct Method Calls (No Pagination)")
        print("-" * 40)
        print("Getting today's events using direct method call...")
        todays_events = calendar.get_todays_events()
        print(f"Found {len(todays_events)} events today")

        for i, event in enumerate(todays_events[:2]):
            print(f"\nEvent {i+1}:")
            print(f"  Title: {event.summary}")
            print(f"  Start: {event.start_time}")
            print(f"  Organizer: {event.organizer_name}")

        # Demo 2: Invoke method calls with pagination
        print("\n2. Invoke Method Calls (With Pagination)")
        print("-" * 40)

        # Calculate date range
        today = datetime.now()
        end_date = today + timedelta(days=30)

        paginated_events = calendar.invoke_tool(
            "get_calendar_entries_by_date_range",
            {
                "start_date": today.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "page": 0,  # First page
            },
        )

        print("Paginated calendar results (page 0):")
        print(f"  Documents in this page: {len(paginated_events['documents'])}")
        print(f"  Has next page: {paginated_events.get('has_next_page', 'N/A')}")
        print(f"  Total documents: {paginated_events.get('total_documents', 'N/A')}")

        # Get next page if available
        if paginated_events.get("has_next_page"):
            print("\nGetting next page...")
            next_page = calendar.invoke_tool(
                "get_calendar_entries_by_date_range",
                {
                    "start_date": today.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "page": 1,  # Second page
                },
            )
            print(f"  Documents in page 1: {len(next_page['documents'])}")

        # Demo 3: Search by topic using both methods
        print("\n3. Search by Topic - Direct vs Invoke")
        print("-" * 40)

        # Direct call
        direct_meetings = calendar.get_calendar_entries_by_topic(
            "meeting", days_ahead=14
        )
        print(f"Direct search for 'meeting': {len(direct_meetings)} events")

        # Invoke call
        invoke_meetings = calendar.invoke_tool(
            "get_calendar_entries_by_topic", {"topic": "meeting", "days_ahead": 14}
        )
        print(
            f"Invoke search for 'meeting': {len(invoke_meetings['documents'])} events in current page"
        )

        # Demo 4: String input with invoke
        print("\n4. String Input for Invoke")
        print("-" * 40)
        string_search = calendar.invoke_tool("get_calendar_entries_by_topic", "standup")
        print(f"String search for 'standup': {len(string_search['documents'])} events")

        # Demo 5: Tool inspection
        print("\n5. Tool Inspection")
        print("-" * 40)
        print("Available tools in Calendar toolkit:")
        for tool_name in calendar.tools.keys():
            tool = calendar.get_tool(tool_name)
            print(f"  - {tool.name}: {tool.description[:60]}...")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please set up OAuth credentials first!")
    except Exception as e:
        print(f"Error accessing Calendar: {e}")


def demo_advanced_features():
    """Demonstrate advanced features like caching and tool integration."""
    print("\n" + "=" * 60)
    print("Advanced Features Demo")
    print("=" * 60)

    try:
        gmail = GmailToolkit()
        calendar = CalendarToolkit()

        # Demo 1: Caching behavior
        print("\n1. Testing Caching Behavior")
        print("-" * 40)
        import time

        print("Making first API call (no cache)...")
        start_time = time.time()
        emails1 = gmail.get_emails_with_body_keyword("test", max_results=5)
        first_call_time = time.time() - start_time

        print("Making second API call (should use cache)...")
        start_time = time.time()
        emails2 = gmail.get_emails_with_body_keyword("test", max_results=5)
        second_call_time = time.time() - start_time

        print(f"First call took: {first_call_time:.2f}s")
        print(f"Second call (cached) took: {second_call_time:.2f}s")
        print(f"Results are identical: {emails1 == emails2}")

        # Demo 2: Caching with invoke calls
        print("\n2. Testing Caching with Invoke Calls")
        print("-" * 40)

        print("First invoke call...")
        start_time = time.time()
        result1 = gmail.invoke_tool(
            "get_emails_with_body_keyword", {"keyword": "test", "max_results": 5}
        )
        first_invoke_time = time.time() - start_time

        print("Second invoke call (should use cache)...")
        start_time = time.time()
        result2 = gmail.invoke_tool(
            "get_emails_with_body_keyword", {"keyword": "test", "max_results": 5}
        )
        second_invoke_time = time.time() - start_time

        print(f"First invoke call took: {first_invoke_time:.2f}s")
        print(f"Second invoke call (cached) took: {second_invoke_time:.2f}s")
        print(f"Results are identical: {result1 == result2}")

        # Demo 3: Pagination across pages uses same cache
        print("\n3. Testing Pagination with Caching")
        print("-" * 40)

        page0 = calendar.invoke_tool(
            "get_calendar_entries_by_date_range",
            {"start_date": "2024-01-01", "end_date": "2024-12-31", "page": 0},
        )

        page1 = calendar.invoke_tool(
            "get_calendar_entries_by_date_range",
            {"start_date": "2024-01-01", "end_date": "2024-12-31", "page": 1},
        )

        print(f"Page 0: {len(page0['documents'])} documents")
        print(f"Page 1: {len(page1['documents'])} documents")
        print(
            f"Both pages have same total_documents: {page0.get('total_documents') == page1.get('total_documents')}"
        )

        # Demo 4: Tool error handling
        print("\n4. Testing Error Handling")
        print("-" * 40)

        try:
            # Try to access non-existent tool
            gmail.get_tool("nonexistent_tool")
        except ValueError as e:
            print(f"Expected error for non-existent tool: {e}")

        # Demo 5: Tool metadata and inspection
        print("\n5. Tool Metadata and Inspection")
        print("-" * 40)

        # Get a tool and inspect it
        search_tool = gmail.get_tool("get_emails_with_body_keyword")
        print(f"Tool name: {search_tool.name}")
        print(f"Tool description: {search_tool.description[:100]}...")

        # Show how to use both direct and invoke
        print("\nThis tool can be used in two ways:")
        print("1. Direct call: gmail.get_emails_with_body_keyword('keyword')")
        print(
            "2. Invoke call: gmail.invoke_tool('get_emails_with_body_keyword', 'keyword')"
        )
        print("   - Direct calls return all results")
        print("   - Invoke calls apply pagination if configured")

    except Exception as e:
        print(f"Error in advanced features demo: {e}")


def demo_tool_comparison():
    """Demonstrate the key differences between direct and invoke calls."""
    print("\n" + "=" * 60)
    print("Direct vs Invoke Call Comparison")
    print("=" * 60)

    try:
        gmail = GmailToolkit()

        print("\nKey Differences:")
        print("1. Direct calls: toolkit.method_name(...)")
        print("   - Return raw results (List[Document])")
        print("   - No pagination applied")
        print("   - Use original function behavior")

        print("\n2. Invoke calls: toolkit.invoke_tool('method_name', {...})")
        print("   - Return serialized results (Dict)")
        print("   - Apply pagination if configured")
        print("   - Provide metadata (page info, token counts)")

        print("\nExample comparison:")
        print("-" * 40)

        # Direct call example
        print("Direct call example:")
        try:
            direct_result = gmail.get_recent_emails(days=3)
            print(f"  Returns: List of {len(direct_result)} EmailDocument objects")
            if direct_result:
                print(f"  First item type: {type(direct_result[0])}")
        except Exception as e:
            print(f"  Error: {e}")

        # Invoke call example
        print("\nInvoke call example:")
        try:
            invoke_result = gmail.invoke_tool("get_recent_emails", {"days": 3})
            print(f"  Returns: Dictionary with keys: {list(invoke_result.keys())}")
            print(f"  Documents count: {len(invoke_result.get('documents', []))}")
            if "page_number" in invoke_result:
                print(
                    f"  Page info: page {invoke_result['page_number']}, has_next: {invoke_result.get('has_next_page', False)}"
                )
        except Exception as e:
            print(f"  Error: {e}")

        print("\nWhen to use which:")
        print(
            "- Use direct calls for: simple scripting, data processing, when you need all results"
        )
        print(
            "- Use invoke calls for: API endpoints, pagination, when integrating with external systems"
        )

    except Exception as e:
        print(f"Error in tool comparison demo: {e}")


def main():
    """Run all demos."""
    print("Google API Toolkits Demo with Tool Integration")
    print("=" * 60)
    print("This demo showcases the new Tool integration that provides:")
    print("- Direct method calls (no pagination)")
    print("- Invoke method calls (with pagination)")
    print("- Caching and error handling")
    print("- Tool inspection and metadata")
    print("=" * 60)

    print(
        "\nMake sure you have set up OAuth credentials in ~/.praga_secrets/credentials.json"
    )

    print("\nRunning demos...")
    demos = [
        demo_gmail_toolkit,
        demo_calendar_toolkit,
        demo_advanced_features,
        demo_tool_comparison,
    ]

    for demo_func in demos:
        try:
            demo_func()
        except Exception as e:
            print(f"Error in {demo_func.__name__}: {e}")
            continue

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
