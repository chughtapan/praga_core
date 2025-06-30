"""Summarization service using OpenAI GPT models."""

import logging
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SummarizationService:
    """Service for generating LLM-based summaries of documents and email threads."""
    
    def __init__(self, openai_client: Optional[OpenAI] = None, model: str = "gpt-4o-mini"):
        """Initialize the summarization service.
        
        Args:
            openai_client: OpenAI client instance. If None, creates a new client
            model: OpenAI model to use for summarization
        """
        self.client = openai_client or OpenAI()
        self.model = model
        logger.info(f"SummarizationService initialized with model: {model}")
    
    def summarize_document(self, title: str, content: str) -> str:
        """Generate a summary for a document.
        
        Args:
            title: Document title
            content: Full document content
            
        Returns:
            A concise summary of the document
        """
        try:

            
            prompt = f"""Please provide a comprehensive summary of the following document in up to 500 words.
Focus on the main topic, key points, purpose, and important details. Be thorough but concise.

Title: {title}

Content: {content}

Summary:"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates detailed document summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=750,  # ~500 words
                temperature=0.3
            )
            
            summary = response.choices[0].message.content
            if summary:
                return summary.strip()
            else:
                logger.warning("OpenAI returned empty summary")
                return self._fallback_summary(content)
                
        except Exception as e:
            logger.error(f"Error generating document summary: {e}")
            return self._fallback_summary(content)
    
    def summarize_email_thread(self, subject: str, emails: List[dict]) -> str:
        """Generate a summary for an email thread.
        
        Args:
            subject: Thread subject
            emails: List of email data (sender, subject, body, time)
            
        Returns:
            A concise summary of the email thread
        """
        try:
            if not emails:
                return "Empty email thread"
            
            # Build a condensed representation of the thread
            thread_text = f"Thread Subject: {subject}\n\n"
            
            for i, email in enumerate(emails):
                sender = email.get('sender', 'Unknown')
                email_subject = email.get('subject', subject)
                body = email.get('body', '')
                # Truncate individual email bodies to keep total size manageable
                truncated_body = body[:500]
                if len(body) > 500:
                    truncated_body += "..."
                
                # Show individual subject if different from thread subject    
                if email_subject != subject:
                    thread_text += f"Email {i+1} from {sender} - Subject: {email_subject}:\n{truncated_body}\n\n"
                else:
                    thread_text += f"Email {i+1} from {sender}:\n{truncated_body}\n\n"
            
            # Truncate the entire thread if too long
            if len(thread_text) > 6000:
                thread_text = thread_text[:6000] + "... [thread truncated]"
            
            prompt = f"""Please provide a comprehensive summary of this email thread in up to 500 words.
Focus on the main topic being discussed, key participants, important decisions or outcomes, and the flow of conversation. Be thorough but concise.

{thread_text}

Summary:"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates detailed email thread summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=750,  # ~500 words
                temperature=0.3
            )
            
            summary = response.choices[0].message.content
            if summary:
                return summary.strip()
            else:
                logger.warning("OpenAI returned empty email thread summary")
                return self._fallback_email_summary(subject, emails)
                
        except Exception as e:
            logger.error(f"Error generating email thread summary: {e}")
            return self._fallback_email_summary(subject, emails)
    
    def _fallback_summary(self, content: str) -> str:
        """Fallback summary when LLM fails - return first 500 chars."""
        summary = content[:500]
        if len(content) > 500:
            summary += "..."
        return summary
    
    def _fallback_email_summary(self, subject: str, emails: List[dict]) -> str:
        """Fallback email thread summary when LLM fails."""
        if not emails:
            return "Empty email thread"
        
        participant_count = len(set(email.get('sender', '') for email in emails))
        return f"Email thread about '{subject}' with {len(emails)} messages from {participant_count} participants." 