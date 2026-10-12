"""Window resize must not increase underlying render buffers."""
import unittest
from warehouse_incident.viewport_memory import configure_viewport

class FakeViewport:
    def __init__(self):
        self.fill_frame=True
        self.resolution_scale=.5
        self.resolution=(640,360)
    def resize_canvas(self,width,height):
        if self.fill_frame:self.resolution=(width,height)

class ViewportMemoryTests(unittest.TestCase):
    def test_maximized_canvas_keeps_capped_render_and_full_scale(self):
        viewport=FakeViewport();record=configure_viewport(viewport)
        viewport.resize_canvas(2560,1600)
        self.assertEqual(viewport.resolution,(960,540))
        self.assertFalse(viewport.fill_frame)
        self.assertEqual(viewport.resolution_scale,1.0)
        self.assertEqual(record['resolution'],[960,540])

if __name__=='__main__':unittest.main()
