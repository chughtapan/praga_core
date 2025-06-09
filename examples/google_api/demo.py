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

        # Demo 1: Get recent emails
        print("\n1. Getting recent emails (last 7 days)...")
        recent_emails = gmail.get_recent_emails(days=7)
        print(f"Found {len(recent_emails)} recent emails")

        # Demo 2: Search by keyword
        print("\n2. Searching emails with keyword 'meeting'...")
        meeting_emails = gmail.get_emails_with_body_keyword("meeting", max_results=5)
        print(f"Found {len(meeting_emails)} emails containing 'meeting'")

        for i, email in enumerate(meeting_emails[:2]):  # Show first 2
            print(f"\nMeeting Email {i+1}:")
            print(f"  Subject: {email.metadata.get('subject', 'N/A')}")
            print(f"  From: {email.metadata.get('from', 'N/A')}")
            print(f"  Date: {email.metadata.get('date', 'N/A')}")
            print(f"  Content preview: {email.content[:150]}...")

        # Demo 3: Get emails by date range
        print("\n3. Getting emails from last week...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        date_range_emails = gmail.get_emails_by_date_range(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            max_results=5,
        )
        print(f"Found {len(date_range_emails)} emails in date range")
        print(
            f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        )

        for i, email in enumerate(date_range_emails[:2]):  # Show first 2
            print(f"\nDate Range Email {i+1}:")
            print(f"  Subject: {email.metadata.get('subject', 'N/A')}")
            print(f"  From: {email.metadata.get('from', 'N/A')}")
            print(f"  Date: {email.metadata.get('date', 'N/A')}")

        # Demo 4: Get any emails (broader search)
        print("\n4. Getting any emails (broader search)...")
        try:
            all_emails = gmail.get_emails_with_body_keyword(
                "", max_results=10
            )  # Empty keyword gets all
            print(f"Found {len(all_emails)} emails with empty keyword search")

            for i, email in enumerate(all_emails[:3]):  # Show first 3
                print(f"\nAny Email {i+1}:")
                print(f"  Subject: {email.metadata.get('subject', 'N/A')}")
                print(f"  From: {email.metadata.get('from', 'N/A')}")
                print(f"  Date: {email.metadata.get('date', 'N/A')}")
        except Exception as e:
            print(f"Error with broad search: {e}")

        # Demo 5: Test pagination
        print("\n5. Testing pagination...")
        paginated_result = gmail.get_emails_with_body_keyword(
            "", page=0
        )  # Get all emails, first page
        print(f"Page 0: {len(paginated_result.documents)} documents")
        print(f"Has next page: {paginated_result.metadata.has_next_page}")
        print(f"Total documents: {paginated_result.metadata.total_documents}")

        if len(paginated_result.documents) > 0:
            print("\nFirst email from pagination:")
            first_email = paginated_result.documents[0]
            print(f"  Subject: {first_email.metadata.get('subject', 'N/A')}")
            print(f"  From: {first_email.metadata.get('from', 'N/A')}")
            print(f"  Date: {first_email.metadata.get('date', 'N/A')}")

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

        # Demo 1: Get today's events
        print("\n1. Getting today's events...")
        todays_events = calendar.get_todays_events()
        print(f"Found {len(todays_events)} events today")

        for i, event in enumerate(todays_events[:3]):  # Show first 3
            print(f"\nEvent {i+1}:")
            print(f"  Title: {event.metadata.get('summary', 'N/A')}")
            print(f"  Start: {event.metadata.get('start_time', 'N/A')}")
            print(f"  Organizer: {event.metadata.get('organizer_name', 'N/A')}")

        # Demo 2: Get upcoming events
        print("\n2. Getting upcoming events (next 7 days)...")
        upcoming_events = calendar.get_upcoming_events(days=7)
        print(f"Found {len(upcoming_events)} upcoming events")

        # Demo 3: Search by topic
        print("\n3. Searching for events with topic 'meeting'...")
        meeting_events = calendar.get_calendar_entries_by_topic(
            "meeting", days_ahead=14
        )
        print(f"Found {len(meeting_events)} events with topic 'meeting'")

        # Demo 4: Get events by date range
        print("\n4. Getting events for next week...")
        today = datetime.now()
        next_week_start = today + timedelta(days=1)
        next_week_end = today + timedelta(days=8)

        next_week_events = calendar.get_calendar_entries_by_date_range(
            next_week_start.strftime("%Y-%m-%d"), next_week_end.strftime("%Y-%m-%d")
        )
        print(f"Found {len(next_week_events)} events for next week")

        # Demo 5: Test pagination
        print("\n5. Testing pagination...")
        paginated_result = calendar.get_calendar_entries_by_date_range(
            (today - timedelta(days=30)).strftime("%Y-%m-%d"),
            (today + timedelta(days=30)).strftime("%Y-%m-%d"),
            page=0,
        )
        print(f"Page 0: {len(paginated_result.documents)} documents")
        print(f"Has next page: {paginated_result.metadata.has_next_page}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please set up OAuth credentials first!")
    except Exception as e:
        print(f"Error accessing Calendar: {e}")


def demo_advanced_features():
    """Demonstrate advanced features like caching and search."""
    print("\n" + "=" * 60)
    print("Advanced Features Demo")
    print("=" * 60)

    try:
        gmail = GmailToolkit()
        calendar = CalendarToolkit()

        # Demo caching
        print("\n1. Testing caching (Gmail)...")
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

        # Demo speculate method
        print("\n2. Testing speculate method...")
        speculations = gmail.speculate("recent emails about meetings")
        print(f"Gmail speculate returned {len(speculations)} suggestions")

        speculations = calendar.speculate("upcoming meetings this week")
        print(f"Calendar speculate returned {len(speculations)} suggestions")

    except Exception as e:
        print(f"Error in advanced features demo: {e}")


def main():
    """Run all demos."""
    print("Google API Toolkits Demo")
    print(
        "Make sure you have set up OAuth credentials in ~/.praga_secrets/credentials.json"
    )

    print("Running demos...")
    demos = [demo_gmail_toolkit, demo_calendar_toolkit, demo_advanced_features]

    for demo_func in demos:
        demo_func()

    print("=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
