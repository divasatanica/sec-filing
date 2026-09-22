"""FastAPI dependency functions."""

from typing import Annotated

from fastapi import Depends, Request

from sec_filing_agent.services.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]
