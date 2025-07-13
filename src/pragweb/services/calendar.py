"""Calendar orchestration service that coordinates between multiple providers."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, cast

from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import CalendarEventPage, PersonPage
from pragweb.toolkit_service import ToolkitService
from pragweb.utils import resolve_person_identifier

logger = logging.getLogger(__name__)


class CalendarService(ToolkitService):
    """Orchestration service for calendar operations across multiple providers."""

    def __init__(self, providers: Dict[str, BaseProviderClient]):
        if not providers:
            raise ValueError("CalendarService requires at least one provider")
        if len(providers) != 1:
            raise ValueError("CalendarService requires exactly one provider")

        self.providers = providers
        super().__init__()
        self._register_handlers()
        logger.info(
            "Calendar service initialized with providers: %s", list(providers.keys())
        )

    @property
    def name(self) -> str:
        """Service name used for registration."""
        # Use provider-specific name to avoid collisions
        provider_name = list(self.providers.keys())[0]
        return f"{provider_name}_calendar"

    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context

        @ctx.route(self.name, cache=True)
        async def handle_event(page_uri: PageURI) -> CalendarEventPage:
            # Parse calendar_id from URI id if present, otherwise use default
            event_id = page_uri.id
            calendar_id = "primary"  # Default calendar

            # If the id contains calendar info (e.g., "event_id@calendar_id"), parse it
            if "@" in event_id:
                event_id, calendar_id = event_id.split("@", 1)

            return await self.create_page(page_uri, event_id, calendar_id)

        # Register calendar actions

        @ctx.action()
        async def update_calendar_event(
            event: CalendarEventPage,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            attendees: Optional[List[PersonPage]] = None,
        ) -> bool:
            """Update a calendar event."""
            try:
                provider = self._get_provider_for_event(event)
                if not provider:
                    return False

                updates: Dict[str, Any] = {}
                if title is not None:
                    updates["title"] = title
                if description is not None:
                    updates["description"] = description
                if location is not None:
                    updates["location"] = location
                if start_time is not None:
                    updates["start_time"] = (
                        start_time.isoformat()
                        if isinstance(start_time, datetime)
                        else start_time
                    )
                if end_time is not None:
                    updates["end_time"] = (
                        end_time.isoformat()
                        if isinstance(end_time, datetime)
                        else end_time
                    )
                if attendees is not None:
                    attendee_emails: List[str] = [person.email for person in attendees]
                    updates["attendees"] = attendee_emails

                await provider.calendar_client.update_event(
                    event_id=event.provider_event_id,
                    calendar_id=event.calendar_id,
                    **updates,
                )

                return True
            except Exception as e:
                logger.error(f"Failed to update calendar event: {e}")
                return False

        @ctx.action()
        async def delete_calendar_event(event: CalendarEventPage) -> bool:
            """Delete a calendar event."""
            try:
                provider = self._get_provider_for_event(event)
                if not provider:
                    return False

                return await provider.calendar_client.delete_event(
                    event_id=event.provider_event_id,
                    calendar_id=event.calendar_id,
                )
            except Exception as e:
                logger.error(f"Failed to delete calendar event: {e}")
                return False

    async def create_page(
        self, page_uri: PageURI, event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        """Create a CalendarEventPage from a Calendar event ID."""
        # 1. Fetch event from Calendar API using shared client
        try:
            provider_client = (
                list(self.providers.values())[0] if self.providers else None
            )
            if not provider_client:
                raise ValueError("No provider available for service")

            event = await provider_client.calendar_client.get_event(
                event_id, calendar_id
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch event {event_id}: {e}")

        # Parse to CalendarEventPage using provider client
        return provider_client.calendar_client.parse_event_to_calendar_page(
            event, page_uri
        )

    async def create_event_page(self, page_uri: PageURI) -> CalendarEventPage:
        """Create a CalendarEventPage from a PageURI.

        Convenience method that extracts event ID and calendar ID from the URI.
        """
        event_id = page_uri.id
        calendar_id = "primary"  # Default calendar

        # If the id contains calendar info (e.g., "event_id@calendar_id"), parse it
        if "@" in event_id:
            event_id, calendar_id = event_id.split("@", 1)

        return await self.create_page(page_uri, event_id, calendar_id)

    @tool()
    async def search_calendar_events(
        self,
        query: str,
        provider: str = "google",
        calendar_id: str = "primary",
        max_results: int = 10,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Search for calendar events across providers.

        Args:
            query: Search query string
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of matching calendar event pages
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search events
            search_results = await provider_client.calendar_client.search_events(
                query=query,
                calendar_id=calendar_id,
                max_results=max_results,
                page_token=cursor,
            )

            # Extract event IDs
            event_ids = []
            for event in search_results.get("items", []):
                event_ids.append(event["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.name,  # Use service name like other services
                    id=event_id,
                )
                for event_id in event_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to CalendarEventPage list for type safety
            event_pages = [
                page for page in pages if isinstance(page, CalendarEventPage)
            ]

            return PaginatedResponse(
                results=event_pages,
                next_cursor=search_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search calendar events: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def get_upcoming_events(
        self,
        provider: str = "google",
        calendar_id: str = "primary",
        max_results: int = 10,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get upcoming calendar events from a provider.

        Args:
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of upcoming calendar event pages
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Get events from now to next 30 days
            now = datetime.now()
            end_time = now + timedelta(days=30)

            # List events
            events_results = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=now,
                time_max=end_time,
                max_results=max_results,
                page_token=cursor,
            )

            # Extract event IDs
            event_ids = []
            for event in events_results.get("items", []):
                event_ids.append(event["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.name,  # Use service name like other services
                    id=event_id,
                )
                for event_id in event_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to CalendarEventPage list for type safety
            event_pages = [
                page for page in pages if isinstance(page, CalendarEventPage)
            ]

            return PaginatedResponse(
                results=event_pages,
                next_cursor=events_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to get upcoming events: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def get_events_for_date(
        self,
        date: datetime,
        provider: str = "google",
        calendar_id: str = "primary",
        max_results: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events for a specific date.

        Args:
            date: Date to get events for
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of calendar event pages for the date
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Get events for the specific date (all day)
            start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)

            # List events
            events_results = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=start_time,
                time_max=end_time,
                max_results=max_results,
                page_token=cursor,
            )

            # Extract event IDs
            event_ids = []
            for event in events_results.get("items", []):
                event_ids.append(event["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.name,
                    id=event_id,
                )
                for event_id in event_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to CalendarEventPage list for type safety
            event_pages = [
                page for page in pages if isinstance(page, CalendarEventPage)
            ]

            return PaginatedResponse(
                results=event_pages,
                next_cursor=events_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to get events for date: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def find_events_with_person(
        self,
        person: PersonPage,
        provider: str = "google",
        calendar_id: str = "primary",
        max_results: int = 10,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Find calendar events that include a specific person.

        Args:
            person: Person to search for
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of calendar event pages with the person
        """
        # Search for events mentioning the person's email
        result = await self.search_calendar_events(
            query=person.email,
            provider=provider,
            calendar_id=calendar_id,
            max_results=max_results,
            cursor=cursor,
        )
        return cast(PaginatedResponse[CalendarEventPage], result)

    @tool()
    async def get_events_by_date_range(
        self,
        start_date: str,
        days: int,
        provider: str = "google",
        calendar_id: str = "primary",
        content: Optional[str] = None,
    ) -> List[CalendarEventPage]:
        """Get events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            days: Number of days from start date
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            content: Optional content filter

        Returns:
            List of calendar event pages in the date range
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return []

        try:
            # Convert start_date string to datetime
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = start_dt + timedelta(days=days)

            # Use provider-specific method for date range filtering
            provider_name = list(self.providers.keys())[0]
            if provider_name == "google":
                events = await self._get_events_by_date_range_google(
                    provider_client, start_dt, end_dt, calendar_id, content
                )
            elif provider_name == "microsoft":
                events = await self._get_events_by_date_range_microsoft(
                    provider_client, start_dt, end_dt, calendar_id, content
                )
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")

            # Convert to CalendarEventPage objects
            event_pages = []
            for event in events:
                page_uri = PageURI(
                    root=self.context.root,
                    type=self.name,
                    id=event["id"],
                )
                event_page = (
                    provider_client.calendar_client.parse_event_to_calendar_page(
                        event, page_uri
                    )
                )
                event_pages.append(event_page)

            return event_pages

        except Exception as e:
            logger.error(f"Failed to get events by date range: {e}")
            return []

    @tool()
    async def get_events_with_person(
        self,
        person_identifier: str,
        provider: str = "google",
        calendar_id: str = "primary",
        content: Optional[str] = None,
    ) -> List[CalendarEventPage]:
        """Get events that include a specific person.

        Args:
            person_identifier: Email address or name of the person
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            content: Optional content filter

        Returns:
            List of calendar event pages that include the person
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return []

        try:
            # Resolve person identifier to email
            email = resolve_person_identifier(person_identifier)

            # Use provider-specific method for person filtering
            provider_name = list(self.providers.keys())[0]
            if provider_name == "google":
                events = await self._get_events_with_person_google(
                    provider_client, email, calendar_id, content
                )
            elif provider_name == "microsoft":
                events = await self._get_events_with_person_microsoft(
                    provider_client, email, calendar_id, content
                )
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")

            # Convert to CalendarEventPage objects
            event_pages = []
            for event in events:
                page_uri = PageURI(
                    root=self.context.root,
                    type=self.name,
                    id=event["id"],
                )
                event_page = (
                    provider_client.calendar_client.parse_event_to_calendar_page(
                        event, page_uri
                    )
                )
                event_pages.append(event_page)

            return event_pages

        except Exception as e:
            logger.error(f"Failed to get events with person: {e}")
            return []

    @tool()
    async def get_upcoming_events_basic(
        self,
        days: int = 7,
        provider: str = "google",
        calendar_id: str = "primary",
        content: Optional[str] = None,
    ) -> List[CalendarEventPage]:
        """Get upcoming events in the next N days.

        Args:
            days: Number of days from today
            provider: Provider to search (google, microsoft, etc.)
            calendar_id: Calendar ID to search
            content: Optional content filter

        Returns:
            List of upcoming calendar event pages
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return []

        try:
            # Get current time and end time
            now = datetime.now()
            end_time = now + timedelta(days=days)

            # Use provider-specific method for upcoming events
            provider_name = list(self.providers.keys())[0]
            if provider_name == "google":
                events = await self._get_upcoming_events_google(
                    provider_client, now, end_time, calendar_id, content
                )
            elif provider_name == "microsoft":
                events = await self._get_upcoming_events_microsoft(
                    provider_client, now, end_time, calendar_id, content
                )
            else:
                raise ValueError(f"Unsupported provider: {provider_name}")

            # Convert to CalendarEventPage objects
            event_pages = []
            for event in events:
                page_uri = PageURI(
                    root=self.context.root,
                    type=self.name,
                    id=event["id"],
                )
                event_page = (
                    provider_client.calendar_client.parse_event_to_calendar_page(
                        event, page_uri
                    )
                )
                event_pages.append(event_page)

            return event_pages

        except Exception as e:
            logger.error(f"Failed to get upcoming events: {e}")
            return []

    def _parse_event_uri(self, page_uri: PageURI) -> tuple[str, str, str]:
        """Parse event URI to extract provider, calendar ID, and event ID."""
        # URI format: event_id (simple format, provider inferred from service)
        # For calendar_id, we'll use "primary" as default
        if not self.providers:
            raise ValueError("No provider available for service")
        provider_name = list(self.providers.keys())[0]
        return provider_name, "primary", page_uri.id

    def _get_provider_for_event(
        self, event: CalendarEventPage
    ) -> Optional[BaseProviderClient]:
        """Get provider client for an event."""
        # Since each service instance has only one provider, return it
        return list(self.providers.values())[0] if self.providers else None

    async def _get_events_by_date_range_google(
        self,
        provider_client: BaseProviderClient,
        start_dt: datetime,
        end_dt: datetime,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get events by date range for Google Calendar."""
        if content:
            # Use search_events with content query for better efficiency
            events_result = await provider_client.calendar_client.search_events(
                query=content, calendar_id=calendar_id, max_results=50
            )
            events: List[Dict[str, Any]] = events_result.get("items", [])

            # Filter by time range since search_events doesn't support time filtering
            filtered_events: List[Dict[str, Any]] = []
            for event in events:
                event_start = event.get("start", {})
                if "dateTime" in event_start:
                    event_time = datetime.fromisoformat(
                        event_start["dateTime"].replace("Z", "+00:00")
                    )
                    # Convert to naive datetime for comparison
                    event_time_naive = event_time.replace(tzinfo=None)
                    if start_dt <= event_time_naive <= end_dt:
                        filtered_events.append(event)
                elif "date" in event_start:
                    event_date = datetime.fromisoformat(event_start["date"])
                    if start_dt.date() <= event_date.date() <= end_dt.date():
                        filtered_events.append(event)
            return filtered_events
        else:
            # Use list_events for time-based filtering (most efficient)
            events_result = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=start_dt,
                time_max=end_dt,
                max_results=50,
            )
            return list(events_result.get("items", []))

    async def _get_events_by_date_range_microsoft(
        self,
        provider_client: BaseProviderClient,
        start_dt: datetime,
        end_dt: datetime,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get events by date range for Microsoft Calendar."""
        if content:
            # Use search_events for content queries (leverages Microsoft Graph search)
            events_result = await provider_client.calendar_client.search_events(
                query=content, calendar_id=calendar_id, max_results=50
            )
            events: List[Dict[str, Any]] = events_result.get("value", [])

            # Filter by time range since search may not support time filtering
            filtered_events: List[Dict[str, Any]] = []
            for event in events:
                event_start = event.get("start", {})
                if "dateTime" in event_start:
                    event_time = datetime.fromisoformat(
                        event_start["dateTime"].replace("Z", "+00:00")
                    )
                    # Convert to naive datetime for comparison
                    event_time_naive = event_time.replace(tzinfo=None)
                    if start_dt <= event_time_naive <= end_dt:
                        filtered_events.append(event)
            return filtered_events
        else:
            # Use list_events with time filtering (uses OData filtering, most efficient)
            events_result = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=start_dt,
                time_max=end_dt,
                max_results=50,
            )
            return list(events_result.get("value", []))

    async def _get_events_with_person_google(
        self,
        provider_client: BaseProviderClient,
        email: str,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get events with person for Google Calendar."""
        # Use search_events with attendee filter for Google
        query = f"attendees:{email}"
        if content:
            query += f" {content}"

        events_result = await provider_client.calendar_client.search_events(
            query=query, calendar_id=calendar_id, max_results=50
        )

        result: List[Dict[str, Any]] = events_result.get("items", [])
        return result

    async def _get_events_with_person_microsoft(
        self,
        provider_client: BaseProviderClient,
        email: str,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get events with person for Microsoft Calendar."""
        # Get all events and filter manually for Microsoft (they may not support attendee search)
        events_result = await provider_client.calendar_client.list_events(
            calendar_id=calendar_id, max_results=50
        )

        all_events: List[Dict[str, Any]] = events_result.get("value", [])

        # Filter events that include the person
        events: List[Dict[str, Any]] = []
        email_lower = email.lower()
        for event in all_events:
            found_person = False

            # Check organizer
            organizer = event.get("organizer", {})
            if (
                organizer.get("emailAddress", {}).get("address", "").lower()
                == email_lower
            ):
                found_person = True

            # Check attendees
            attendees = event.get("attendees", [])
            for attendee in attendees:
                if (
                    attendee.get("emailAddress", {}).get("address", "").lower()
                    == email_lower
                ):
                    found_person = True
                    break

            if found_person:
                events.append(event)

        # Filter by content if specified
        if content:
            content_lower = content.lower()
            filtered_events: List[Dict[str, Any]] = []
            for event in events:
                if (
                    content_lower in event.get("subject", "").lower()
                    or content_lower in event.get("body", {}).get("content", "").lower()
                    or content_lower
                    in event.get("location", {}).get("displayName", "").lower()
                ):
                    filtered_events.append(event)
            events = filtered_events

        return events

    async def _get_upcoming_events_google(
        self,
        provider_client: BaseProviderClient,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get upcoming events for Google Calendar."""
        if content:
            # Use search_events with content query for better efficiency
            events_result = await provider_client.calendar_client.search_events(
                query=content, calendar_id=calendar_id, max_results=50
            )
            events: List[Dict[str, Any]] = events_result.get("items", [])

            # Filter by time range since search_events doesn't support time filtering
            filtered_events: List[Dict[str, Any]] = []
            for event in events:
                event_start = event.get("start", {})
                if "dateTime" in event_start:
                    event_time = datetime.fromisoformat(
                        event_start["dateTime"].replace("Z", "+00:00")
                    )
                    # Convert to naive datetime for comparison
                    event_time_naive = event_time.replace(tzinfo=None)
                    if start_time <= event_time_naive <= end_time:
                        filtered_events.append(event)
                elif "date" in event_start:
                    event_date = datetime.fromisoformat(event_start["date"])
                    if start_time.date() <= event_date.date() <= end_time.date():
                        filtered_events.append(event)
            return filtered_events
        else:
            # Use list_events for time-based filtering (most efficient)
            events_result = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=start_time,
                time_max=end_time,
                max_results=50,
            )
            return list(events_result.get("items", []))

    async def _get_upcoming_events_microsoft(
        self,
        provider_client: BaseProviderClient,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str,
        content: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Get upcoming events for Microsoft Calendar."""
        if content:
            # Use search_events for content queries (leverages Microsoft Graph search)
            events_result = await provider_client.calendar_client.search_events(
                query=content, calendar_id=calendar_id, max_results=50
            )
            events: List[Dict[str, Any]] = events_result.get("value", [])

            # Filter by time range since search may not support time filtering
            filtered_events: List[Dict[str, Any]] = []
            for event in events:
                event_start = event.get("start", {})
                if "dateTime" in event_start:
                    event_time = datetime.fromisoformat(
                        event_start["dateTime"].replace("Z", "+00:00")
                    )
                    # Convert to naive datetime for comparison
                    event_time_naive = event_time.replace(tzinfo=None)
                    if start_time <= event_time_naive <= end_time:
                        filtered_events.append(event)
            return filtered_events
        else:
            # Use list_events with time filtering (uses OData filtering, most efficient)
            events_result = await provider_client.calendar_client.list_events(
                calendar_id=calendar_id,
                time_min=start_time,
                time_max=end_time,
                max_results=50,
            )
            return list(events_result.get("value", []))
