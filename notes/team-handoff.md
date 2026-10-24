# Team handoff — NPL GIS

**Repository:** https://github.com/davidtwmak-maker/NPLGIS
**Live site:** https://davidtwmak-maker.github.io/NPLGIS/
**3D app:** https://davidtwmak-maker.github.io/NPLGIS/apps/festival-walk-3d/

## What is in this folder

| Item | What it is |
|---|---|
| `nplgis/` | The full project working tree — 3D app, maps, data, scripts, notes. **No `.git` history.** |
| `nplgis-team-repo.zip` | The same project as a zip, built from the published commit (`bb58066`). |

Both copies are identical to the published commit and were checked byte-for-byte.

## Uploading an update to GitHub

The published repo already exists, so the quickest route is to clone it:

```bash
git clone https://github.com/davidtwmak-maker/NPLGIS.git
cd NPLGIS
# edit files
git add -A
git commit -m "Describe your change"
git push origin main
```

You need a GitHub **personal access token**, not your account password. Give it the
`repo` scope, and also tick **`workflow`** — GitHub rejects any push that edits
`.github/workflows/deploy.yml` without it.

Using the GitHub CLI instead:

```bash
gh auth login
gh auth setup-git
gh auth refresh -h github.com -s workflow
```

### If you start from the `nplgis/` folder in this drive

It has no `.git`, so set it up as a clone **before** you edit anything:

```bash
cd nplgis
git init
git remote add origin https://github.com/davidtwmak-maker/NPLGIS.git
git fetch --depth=1 origin main
git reset --hard origin/main
git branch --set-upstream-to=origin/main main
git status        # should be clean
```

`git reset --hard` is the important line — it lines the folder up with the published
commit instead of treating every file as new. Do this **before** you edit anything.

## After you push

GitHub Actions rebuilds and redeploys the site automatically. Check the **Actions** tab
— the run must be green before the change shows on the live site. The URL never changes.

## Files deliberately not included

`raw/`, `lidar_dtm/` and `tiles_ib20000/` are excluded by `.gitignore`: they are large
source downloads rather than deliverables. Run the matching `scripts/fetch_*.sh` to get
them back.

## Things to know before you quote the 3D model

- **The storey height (5.5 m) is schematic**, drawn at 1× vertical scale. It is not a
  measured building.
- **The height datum is the ground floor G** (0 m): MTR −16.5 m, LG2 −11.0, LG1 −5.5,
  G 0, UG +5.5, 1/F +11.0, 2/F +16.5.
- **1/F and 2/F are massing only** — CSDI publishes route data for five floors, so the two
  upper floors are drawn inset from the G-floor envelope and marked `體量`.
- **Floor outlines come from pedestrian-route extents**, not official floor plans.
- **The office tower is excluded** — the model is the mall only.
