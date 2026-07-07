# CV Codebase — GitHub Pages

This site hosts a static GitHub Pages project along with mirrored data and tooling from the
[Idaho National Laboratory CIE_EC_Database](https://github.com/idaholab/CIE_EC_Database).

## Live site

- Home: [https://christianvdbag.github.io/cvcodebase/](https://christianvdbag.github.io/cvcodebase/)
- This README: [https://christianvdbag.github.io/cvcodebase/README.md](https://christianvdbag.github.io/cvcodebase/README.md)

## Resources

The following files are cloned into this repository and served directly from GitHub Pages.

| Resource | Local (Pages) link | Upstream source |
| --- | --- | --- |
| Engineered Controls Dashboard (HTML) | [engineered_controls_dashboard.html](external/CIE_EC_Database/engineered_controls_dashboard.html) | [idaholab/CIE_EC_Database](https://github.com/idaholab/CIE_EC_Database/blob/main/gui/engineered_controls_dashboard.html) |
| IDF data (`idf.min.json`) | [idf.min.json](external/CIE_EC_Database/idf.min.json) | [idaholab/CIE_EC_Database](https://github.com/idaholab/CIE_EC_Database/blob/main/gui/idf.min.json) |
| Engineered Controls data (`engctrls-V2_JSON.zip`) | [engctrls-V2_JSON.zip](external/CIE_EC_Database/engctrls-V2_JSON.zip) | [idaholab/CIE_EC_Database](https://github.com/idaholab/CIE_EC_Database/blob/main/data/engctrls-V2_JSON.zip) |

### Absolute Pages URLs

- Dashboard: https://christianvdbag.github.io/cvcodebase/external/CIE_EC_Database/engineered_controls_dashboard.html
- IDF JSON: https://christianvdbag.github.io/cvcodebase/external/CIE_EC_Database/idf.min.json
- Data ZIP: https://christianvdbag.github.io/cvcodebase/external/CIE_EC_Database/engctrls-V2_JSON.zip

## Local preview

```bash
cd gh-pages-site
python -m http.server 4173
```

Then open http://localhost:4173.

## Deployment

This site is published from the `gh-pages-site/` folder via GitHub Actions
(`.github/workflows/deploy-gh-pages-site.yml`) on every push to `main`.

## Attribution

Mirrored data and the dashboard originate from the
[idaholab/CIE_EC_Database](https://github.com/idaholab/CIE_EC_Database) project.
Please refer to that repository for licensing and authoritative updates.
