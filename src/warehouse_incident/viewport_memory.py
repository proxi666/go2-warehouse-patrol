"""Keep editor render allocation independent of desktop/window dimensions."""

def configure_viewport(viewport):
    """Apply the bounded laptop canvas before loading a rendered scene."""
    viewport.fill_frame=False
    viewport.resolution_scale=1.0
    viewport.resolution=(960,540)
    return {'resolution':list(viewport.resolution),
            'scale':viewport.resolution_scale,'fill_frame':viewport.fill_frame}
