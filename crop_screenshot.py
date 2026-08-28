from PIL import Image

image_path = r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\media__1781791647727.png"
img = Image.open(image_path)
width, height = img.size
print("Image size:", width, height)

# Let's crop the bottom right section (e.g. from x = 0.5*width to width, y = 0.5*height to height)
# Or let's divide it into 8 screens.
# Since it's a 8-screen layout, let's divide the width by 4 and height by 2.
# Screens are:
# Row 1: S1, S2, S3, S4
# Row 2: S5, S6, S7, S8
# S8 is the bottom right screen.
s_width = width // 4
s_height = height // 2

# Let's crop S8 (bottom right)
crop_s8 = img.crop((s_width * 3, s_height, width, height))
crop_s8.save(r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\s8_crop.png")
print("S8 cropped and saved.")

# Also let's crop S7 (bottom row, third screen) which might contain the console
crop_s7 = img.crop((s_width * 2, s_height, s_width * 3, height))
crop_s7.save(r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\s7_crop.png")
print("S7 cropped and saved.")

# Also let's crop S3 (top row, third screen)
crop_s3 = img.crop((s_width * 2, 0, s_width * 3, s_height))
crop_s3.save(r"C:\Users\Ismael Romero\.gemini\antigravity\brain\63c80efb-e588-4e13-9a8c-2b4636f0c6a2\s3_crop.png")
print("S3 cropped and saved.")
