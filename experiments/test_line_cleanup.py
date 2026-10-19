from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from experiments.line_cleanup import clean_lines, export


class CleanupTests(unittest.TestCase):
    def test_gray_blocks_removed_lines_dashes_and_small_marks_retained(self):
        image = Image.new('RGB', (120, 100), (245, 245, 245))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 60, 70), fill=(205, 205, 205))
        draw.line((20, 20, 100, 80), fill='black', width=1)
        draw.line((80, 10, 80, 20), fill=(110, 110, 110), width=1)
        draw.line((80, 25, 80, 35), fill=(110, 110, 110), width=1)
        draw.point((6, 6), fill='black')
        result = clean_lines(image, smooth=0).smoothed
        self.assertEqual(result.getpixel((10, 60))[3], 0)
        self.assertEqual(result.getpixel((20, 20)), (0, 0, 0, 255))
        self.assertEqual(result.getpixel((80, 15))[3], 255)
        self.assertEqual(result.getpixel((80, 23))[3], 0)
        self.assertEqual(result.getpixel((6, 6))[3], 255)

    def test_smooth_alpha_only_and_single_ink(self):
        image = Image.new('RGB', (40, 40), 'white')
        ImageDraw.Draw(image).line((10, 10, 30, 28), fill='black', width=2)
        result = clean_lines(image, smooth=.5, ink='#1565c0').smoothed
        pixels = np.asarray(result)
        self.assertTrue(np.any((pixels[:, :, 3] > 0) & (pixels[:, :, 3] < 255)))
        self.assertTrue(np.all(pixels[:, :, :3] == [21, 101, 192]))
        self.assertEqual(result.getpixel((0, 0))[3], 0)

    def test_transparent_input_stays_transparent(self):
        source = Image.new('RGBA', (20, 20), (0, 0, 0, 0))
        ImageDraw.Draw(source).rectangle((5, 5, 15, 15), fill=(0, 0, 0, 128))
        result = clean_lines(source, smooth=0).smoothed
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((10, 10))[3], 128)

    def test_png_export_and_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Image.new('RGB', (20, 20), 'white')
            ImageDraw.Draw(source).line((4, 4, 16, 16), fill='black')
            export(source, folder)
            with Image.open(Path(folder)/'03-smoothed.png') as result:
                self.assertEqual(result.mode, 'RGBA')
                self.assertEqual(result.getpixel((0, 0))[3], 0)
            with self.assertRaises(ValueError):
                export(source, folder)

    def test_empty_and_invalid_parameters(self):
        with self.assertRaises(ValueError): clean_lines(Image.new('RGB', (20, 20), 'white'))
        for options in [dict(threshold=255), dict(smooth=-1), dict(smooth=float('nan'))]:
            with self.assertRaises(ValueError): clean_lines(Image.new('RGB', (20, 20), 'black'), **options)


if __name__ == '__main__':
    unittest.main()
