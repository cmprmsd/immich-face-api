Yes it's a vibedump. However face detection works flawlessly and always within <200ms if you set the Model unload time to 0 . :)

```bash
# Keep models in VRAM (0 = never unload; default 300s unloads after 5 min idle)
      MACHINE_LEARNING_MODEL_TTL: "0"
```