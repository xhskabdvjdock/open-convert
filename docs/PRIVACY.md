# Privacy

This local milestone does not require an account or analytics. Images are sent to the configured API, inspected and converted in memory, and returned in the HTTP response. The service does not persist job metadata or image files. The browser holds the response blob until the page is closed or the user starts another conversion.

For a hosted deployment, disclose the hosting provider and processing location before accepting uploads. This milestone does not implement a hosted service, retention scheduler, or forensic deletion guarantee.
