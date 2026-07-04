# Live2D Web Runtime placement

No runtime files are bundled because their licenses and distribution terms must be reviewed separately.

The preview page currently expects compatible builds named:

- `pixi.min.js`
- `live2dcubismcore.min.js`
- `cubism4.min.js` (`pixi-live2d-display` Cubism 4 bundle)

Obtain them from their official projects or your licensed Live2D Cubism SDK for Web package. Confirm redistribution rights before packaging them with Maidie.

Runtime bundles and model assets are intentionally ignored by Git. Do not commit official Sample models, `.moc3`, textures, motions, expressions, physics data, or your local model directory.

Install the optional Qt browser component with a version compatible with the project's PyQt6:

```powershell
python -m pip install -r requirements-live2d.txt
```

The Viewer is only used by the independent preview dialog. It does not replace Maidie's main Sprite desktop-pet renderer. Missing WebEngine or Runtime files must remain a recoverable preview error.
