# GitHub Pages Subproject

This folder is a standalone static site ready for GitHub Pages deployment.

## Local preview

Open `index.html` directly in a browser, or run a local static file server.

Example:

```bash
cd gh-pages-site
python -m http.server 4173
```

Then open http://localhost:4173.

## Deployment

A repository-level workflow publishes this folder to GitHub Pages:

- Workflow file: `.github/workflows/deploy-gh-pages-site.yml`
- Source path: `gh-pages-site/`
- Trigger: push to `main` or manual dispatch
