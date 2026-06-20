# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
import pandas as pd
import traceback
from shapely import wkt
from shapely.ops import unary_union
from shapely.geometry import Polygon
import math
import geopandas as gpd

class NDMOutAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("NDM/vNDM Output Analyzer J.Liria & A.Y. Soto-Vivas, 2026")
        self.file_paths = []

        self.min_score = tk.DoubleVar(value=0.0)
        self.max_score = tk.DoubleVar(value=1.0)
        self.include_grp = tk.BooleanVar(value=False)

        self.create_widgets()
    
    def create_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        tk.Button(frame, text="Load .OUT Files", command=self.load_files).grid(row=0, column=0, pady=5, sticky="ew")
        self.file_count_label = tk.Label(frame, text="No files loaded")
        self.file_count_label.grid(row=0, column=1, pady=5, sticky="w")

        tk.Label(frame, text="Min Score").grid(row=1, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.min_score).grid(row=1, column=1)

        tk.Label(frame, text="Max Score").grid(row=2, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.max_score).grid(row=2, column=1)

        tk.Checkbutton(
            frame,
            text="Include GRP- categories",
            variable=self.include_grp
        ).grid(row=3, columnspan=2, sticky="w")
               
        tk.Button(
            frame,
            text="Individual and Consensus Endemic Areas Analysis",
            command=self.run_analysis
        ).grid(row=4, columnspan=2, pady=10, sticky="ew")
                
        tk.Button(
            frame,
            text="Geospatial Consensus Analysis",
            command=self.run_geospatial_consensus_analysis
        ).grid(row=5, columnspan=2, pady=5, sticky="ew")

        # Mosaic PNG from WKT (conX_N.csv)
        tk.Button(
            frame,
            text="Export Consensus Mosaics",
            command=self.plot_consensus_mosaic
        ).grid(row=6, columnspan=2, pady=5, sticky="ew")

        tk.Label(frame, text="Analysis Summary:").grid(row=7, columnspan=2, sticky="w", pady=(10, 0))
        self.summary_text = tk.Text(frame, height=10, width=50, state="disabled", wrap=tk.WORD)
        self.summary_text.grid(row=8, columnspan=2, pady=(0, 10), sticky="nsew")

        scrollbar = tk.Scrollbar(frame, command=self.summary_text.yview)
        scrollbar.grid(row=8, column=2, sticky='ns')
        self.summary_text.config(yscrollcommand=scrollbar.set)

    def load_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("NDM Output", "*.out")])
        if paths:
            self.file_paths = list(paths)
            self.file_count_label.config(text=f"{len(self.file_paths)} file(s) loaded.")
            messagebox.showinfo("Files Loaded", f"Loaded {len(self.file_paths)} file(s).")
        else:
            self.file_paths = []
            self.file_count_label.config(text="No files loaded")

    def update_summary(self, text_content, append=False):
        self.summary_text.config(state="normal")
        if not append:
            self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(tk.END, text_content)
        self.summary_text.see(tk.END)
        self.summary_text.config(state="disabled")
        self.root.update_idletasks()

    def run_geospatial_consensus_analysis(self):
        """
        Analyze consensus files with con*/point* prefix and generate a new Excel:
          1_Consensus_Summary
          2_Consensus_Overlap
          3_Shared_Species
        """
        # Import geospatial libraries
        try:
            from shapely import wkt
            from shapely.ops import unary_union
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "This feature requires the 'shapely' library.\nInstall it with:\n\npip install shapely"
            )
            return

        # Select folder containing conX_N.csv and pointX_N.csv
        folder_root = filedialog.askdirectory(
            title="Select root folder containing grid-size subfolders (2.5, 5, 10, 12.5, 15...)"
        )
        if not folder_root:
            return

        self.update_summary(f"Selected root folder:\n{folder_root}\n\n", append=True)

        # Detect subfolders (treatments/scenarios).
        grid_folders = []  # List of tuples: (folder_label, folder_path)

        for item in os.listdir(folder_root):
            path = os.path.join(folder_root, item)
            if os.path.isdir(path):
                folder_label = item.strip()
                if folder_label:  
                    grid_folders.append((folder_label, path))

        # Sort: if the name is numeric, sort numerically; otherwise, sort alphabetically.
        def _folder_sort_key(t):
            label = t[0].replace(",", ".")
            try:
                return (0, float(label))
            except ValueError:
                return (1, label.lower())

        grid_folders.sort(key=_folder_sort_key)

        if not grid_folders:
            messagebox.showwarning(
                "No subfolders found",
                "No subfolders were found inside the selected root folder."
            )
            return

        self.update_summary(f"Detected subfolders (treatments): {[g for g, _ in grid_folders]}\n\n", append=True)

        # Master dictionaries
        consensus_sets = {}     # key=(grid_size, cid, total) → {'poly':..., 'point':...}
        label_by_key = {}       # key → '2.5deg_con0_26'

        pattern_con = re.compile(r'^con(\d+)_(\d+)\.csv$', re.IGNORECASE)
        pattern_point = re.compile(r'^point(\d+)_(\d+)\.csv$', re.IGNORECASE)

        # Process each folder (treatment)
        for folder_label, grid_dir in grid_folders:
            self.update_summary(f"\nScanning folder '{folder_label}': {grid_dir}\n", append=True)

            try:
                files = os.listdir(grid_dir)
            except Exception as e:
                self.update_summary(f"  ERROR listing {grid_dir}: {e}\n", append=True)
                continue

            for fname in files:
                m_con = pattern_con.match(fname)
                if m_con:
                    cid = int(m_con.group(1))
                    total = int(m_con.group(2))
                    key = (folder_label, cid, total)

                    consensus_sets.setdefault(key, {})['poly'] = os.path.join(grid_dir, fname)
                    label_by_key[key] = f"{folder_label}_con{cid}_{total}"
                    continue

                m_pt = pattern_point.match(fname)
                if m_pt:
                    cid = int(m_pt.group(1))
                    total = int(m_pt.group(2))
                    key = (folder_label, cid, total)

                    consensus_sets.setdefault(key, {})['point'] = os.path.join(grid_dir, fname)
                    label_by_key[key] = f"{folder_label}_con{cid}_{total}"

        # Filter only the consensus cases that have both files
        valid_keys = [k for k, v in consensus_sets.items() if 'poly' in v and 'point' in v]
        if not valid_keys:
            messagebox.showwarning(
                "No consensus pairs found",
                "No matching pairs conX_N.csv / pointX_N.csv were found in the selected folder."
            )
            return

        self.update_summary(f"Found {len(valid_keys)} consensus sets with polygons and points.\n\n", append=True)

        consensus_info = []        # For sheet 1
        geom_by_key = {}           # (cid, total) -> geometry
        species_by_key = {}        # (cid, total) -> set(species)
        area_by_key = {}           # (cid, total) -> area
        
        # Natural sorting by treatment: numeric priority, fallback to alphabetical
        def _grid_sort_val(lbl):
            s = str(lbl).replace(",", ".")
            try:
                return (0, float(s))
            except ValueError:
                return (1, s.lower())

        valid_keys = sorted(valid_keys, key=lambda k: (_grid_sort_val(k[0]), k[1], k[2]))

        # --------------------------------------------------------
        # Helper: Find key (grid, cid, total) a partir de grid+cid
        # -------------------------------------------------------
        def find_key(grid, cid):
            for (g, c, t) in consensus_sets.keys():
                if g == grid and c == cid:
                    return (g, c, t)
            return None

        # ================================================
        # PROCESSING LOOP FOR EACH CONSENSUS (VALIDATED)
        # ================================================

        for folder_label, cid, total in valid_keys:

            files = consensus_sets[(folder_label, cid, total)]
            poly_path = files['poly']
            point_path = files['point']

            self.update_summary(
                f"Processing consensus {cid} of {total} "
                f"(Folder '{folder_label}')\n",
                append=True
            )

            # --- Read polygon files ---
            try:
                df_poly = pd.read_csv(poly_path)
            except Exception as e:
                self.update_summary(
                    f"  ERROR reading polygon file {os.path.basename(poly_path)}: {e}\n",
                    append=True
                )
                continue
     
            polygon = None

            # Case 1: column WKT
            wkt_col = None
            for col in df_poly.columns:
                if col.strip().upper() == 'WKT':
                    wkt_col = col
                    break

            if wkt_col is not None:
                try:
                    geoms = df_poly[wkt_col].dropna().apply(lambda s: wkt.loads(str(s)))
                    polygon = unary_union(list(geoms))
                except Exception as e:
                    self.update_summary(f"  ERROR parsing WKT: {e}\n", append=True)
                    continue

            else:
                # Case 2: Coord columns (lon/lat)
                lon_col = None
                lat_col = None

                for col in df_poly.columns:
                    c = col.strip().lower()
                    if c in ('lon', 'long', 'longitude', 'x'):
                        lon_col = col
                    elif c in ('lat', 'latitude', 'y'):
                        lat_col = col

                if lon_col is None or lat_col is None:
                    self.update_summary(
                        f"  ERROR: No WKT or coordinate columns found in {os.path.basename(poly_path)}\n",
                        append=True
                    )
                    continue

                try:
                    polygon = Polygon(zip(df_poly[lon_col], df_poly[lat_col]))
                except Exception as e:
                    self.update_summary(f"  ERROR building polygon: {e}\n", append=True)
                    continue

            # --- Point file ---
            try:
                df_points = pd.read_csv(point_path, sep=None, engine="python")
            except Exception as e:
                self.update_summary(f"  ERROR reading points: {e}\n", append=True)
                continue

            # Detect species column
            species_col = None
            for col in df_points.columns:
                c = col.strip().upper()
                if c in ("SPECIES", "ESPECIE", "SP", "TAXON", "SCIENTIFIC_NAME", "NAME"):
                    species_col = col
                    break

            if species_col is None:
                self.update_summary(
                    f"  ERROR: No species column found in {os.path.basename(point_path)}. "
                    f"Columns={list(df_points.columns)}\n",
                    append=True
                )
                continue

            species = set(df_points[species_col].dropna().astype(str).str.strip())

            # --- Save geometry and species ---
            key = (folder_label, cid, total)

            geom_by_key[key] = polygon
            species_by_key[key] = species

            consensus_info.append({
                'Treatment': folder_label,   
                'Consensus_ID': cid,
                'Total_Consensus': total,
                'N_Species': len(species),
                'Polygon_Area': polygon.area,
                'File': os.path.basename(poly_path)
            })

            area_by_key[key] = float(polygon.area)
            label_by_key[key] = f"{folder_label}:con{cid}_{total}"

        if not consensus_info:
                messagebox.showwarning(
                    "No valid consensus",
                    "No valid consensus geometries could be built."
                )
                return

        df_summary = pd.DataFrame(consensus_info)

        # -------------------------------------------------
        # 2) Overlap across and within grids
        # -------------------------------------------------
        overlap_records = []
        keys = sorted(geom_by_key.keys(), key=lambda k: (_grid_sort_val(k[0]), k[1], k[2]))

        self.update_summary("\nComputing overlaps within and across grid sizes or treatments...\n", append=True)

        for i in range(len(keys)):
            gA, cidA, totA = keys[i]
            geomA = geom_by_key[keys[i]]
            areaA = area_by_key[keys[i]]

            speciesA = species_by_key.get(keys[i], set())  

            for j in range(i + 1, len(keys)):
                gB, cidB, totB = keys[j]
                geomB = geom_by_key[keys[j]]
                areaB = area_by_key[keys[j]]

                speciesB = species_by_key.get(keys[j], set())  

                # --- Spatial overlap ---
                if geomA.intersects(geomB):
                    inter = geomA.intersection(geomB)
                    overlap_area = inter.area
                else:
                    overlap_area = 0.0

                union_area = areaA + areaB - overlap_area
                jaccard = overlap_area / union_area if union_area > 0 else 0.0

                # --- Beta diversity ---
                a = len(speciesA & speciesB)
                b = len(speciesA - speciesB)
                c = len(speciesB - speciesA)

                # Jaccard taxonomic dissimilarity
                union_tax = a + b + c
                beta_jaccard = 1 - (a / union_tax) if union_tax > 0 else 0.0

                # Sørensen dissimilarity
                beta_sorensen = (b + c) / (2*a + b + c) if (2*a + b + c) > 0 else 0.0

                # Baselga decomposition
                min_bc = min(b, c)
                beta_turnover = min_bc / (a + min_bc) if (a + min_bc) > 0 else 0.0
                beta_nestedness = beta_sorensen - beta_turnover

                overlap_records.append({
                    "Grid_A": gA,
                    "Consensus_A": cidA,
                    "Consensus_A_Name": label_by_key[keys[i]],

                    "Grid_B": gB,
                    "Consensus_B": cidB,
                    "Consensus_B_Name": label_by_key[keys[j]],

                    # Spatial metrics
                    "Area_A": areaA,
                    "Area_B": areaB,
                    "Overlap_Area": overlap_area,
                    "Jaccard_Area": jaccard,

                    # Taxonomic overlap
                    "N_Shared_Species": a,
                    "N_Union_Species": union_tax,

                    # Beta diversity metrics
                    "Beta_Jaccard_Tax": beta_jaccard,
                    "Beta_Sorensen": beta_sorensen,
                    "Beta_Turnover_Simpson": beta_turnover,
                    "Beta_Nestedness": beta_nestedness
                })

        df_overlap = pd.DataFrame(overlap_records)

        # -------------------------------------------------
        # 3) Shared species and genera (within & across grids)
        # -------------------------------------------------
        shared_records = []

        if not df_overlap.empty:
            self.update_summary("Computing shared species and genera across grids or treatments...\n", append=True)

            for _, row in df_overlap.iterrows():
                keyA = find_key(row["Grid_A"], row["Consensus_A"])
                keyB = find_key(row["Grid_B"], row["Consensus_B"])

                if keyA is None or keyB is None:
                    continue  

                sppA = species_by_key.get(keyA, set())
                sppB = species_by_key.get(keyB, set())

                shared_species = sppA.intersection(sppB)

                genusA = {s.split("_")[0] for s in sppA}
                genusB = {s.split("_")[0] for s in sppB}
                shared_genera = genusA.intersection(genusB)

                exclusive_species_A = sppA - shared_species
                exclusive_species_B = sppB - shared_species

                exclusive_genera_A = genusA - shared_genera
                exclusive_genera_B = genusB - shared_genera

                shared_records.append({
                    "Grid_A": row["Grid_A"],
                    "Consensus_A_Name": row["Consensus_A_Name"],
                    "Grid_B": row["Grid_B"],
                    "Consensus_B_Name": row["Consensus_B_Name"],

                    "N_Shared_Species": len(shared_species),
                    "Shared_Species": "; ".join(sorted(shared_species)),

                    "N_Shared_Genera": len(shared_genera),
                    "Shared_Genera": "; ".join(sorted(shared_genera)),

                    "N_Species_A": len(sppA),
                    "N_Species_B": len(sppB),

                    "N_Exclusive_Species_A": len(exclusive_species_A),
                    "N_Exclusive_Species_B": len(exclusive_species_B),

                    "Exclusive_Genera_A": "; ".join(sorted(exclusive_genera_A)),
                    "Exclusive_Genera_B": "; ".join(sorted(exclusive_genera_B)),
                })
        
        if shared_records:
            df_shared = pd.DataFrame(shared_records)
        else:
            df_shared = pd.DataFrame(columns=[
                "Grid_A", "Consensus_A_Name",
                "Grid_B", "Consensus_B_Name",
                "N_Shared_Species", "Shared_Species",
                "N_Shared_Genera", "Shared_Genera",
                "N_Species_A", "N_Species_B",
                "N_Exclusive_Species_A", "N_Exclusive_Species_B",
                "Exclusive_Genera_A", "Exclusive_Genera_B"
            ])

        # -------------------------------------------------
        # 4) Save geospatial data to Excel
        # -------------------------------------------------
        output_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="Save geospatial consensus analysis Excel"
        )
        if not output_path:
            self.update_summary("Geospatial export cancelled by user.\n", append=True)
            return

        try:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df_summary.to_excel(writer, sheet_name="1_Consensus_Summary", index=False)
                df_overlap.to_excel(writer, sheet_name="2_Consensus_Overlap", index=False)
                df_shared.to_excel(writer, sheet_name="3_Shared_Species", index=False)
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save geospatial Excel file:\n{e}")
            return

        self.update_summary(f"\nGeospatial analysis complete.\nFile saved as:\n{output_path}\n", append=True)
        messagebox.showinfo("Done", f"Geospatial consensus analysis completed.\nFile saved as:\n{output_path}")
           
    def extract_species_represented(self, text):
        match = re.search(r"Species represented:\s*(.*?)\Z", text, re.DOTALL)
        if not match:
            return []
        lines = match.group(1).strip().splitlines()
        species = []
        for line in lines:
            parts = re.split(r"\s*\d+\.\s*", line.strip())
            for part in parts:
                clean = part.strip()
                if clean:
                    species.append(clean)
        return species

    def extract_consensus_area_details_fixed(self, text):
        import re
        consensus_blocks = re.findall(r'SET NR\.\s+(\d+), size (\d+), score ([\d.]+)\s+(\d+) scoring spp\. \(sp/score\):(.*?)\n\n', text, re.DOTALL)

        results = {}
        for block in consensus_blocks:
            set_id = int(block[0])
            score = float(block[2])
            species_block = block[4].strip()

            # Extract species and their scores
            species_lines = species_block.splitlines()
            species_data = []
            for line in species_lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    species_name = parts[0]
                    try:
                        species_score = float(parts[1])
                    except ValueError:
                        continue
                    species_data.append((species_name, species_score))

            results[set_id] = species_data

        return results

    def build_species_map_fixed(self, file_paths, min_score, max_score, include_grp):
        import re
        species_map = {}

        for path in file_paths:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            filename = os.path.basename(path)
            current_set_id = None
            inside_set = False

            for i, line in enumerate(lines):
                # Detect the beginning of a data SET
                if line.strip().startswith("SET NR."):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        try:
                            current_set_id = int(parts[2].rstrip(','))
                            inside_set = False  
                        except ValueError:
                            current_set_id = None
                            continue

                # Detect line containing "scoring spp."
                if "scoring spp." in line:
                    inside_set = True
                    continue

                # Read species score
                if inside_set:
                    if line.strip() == "" or not line[0].isspace():
                        inside_set = False
                        continue

                    match = re.match(r'\s*\d+\s+([^\s]+)\s*:\s*([\d.]+)', line)
                    if match and current_set_id is not None:
                        species_name = match.group(1)
                        score = float(match.group(2))
                        if include_grp or not species_name.startswith("GRP-"):
                            if min_score <= score <= max_score:
                                key = (filename, current_set_id)
                                if key not in species_map:
                                    species_map[key] = []
                                species_map[key].append((species_name, score))

        return species_map

    def _parse_score_string(self, score_str, id_context, file_basename, context_type):
        try:
            if '(' in score_str:
                min_score, max_score = map(float, score_str.strip('()').split('-'))
                return min_score, max_score
            else:
                score_value = float(score_str)
                return score_value, score_value
        except ValueError:
            messagebox.showwarning("Score Format Error",
                                   f"Skipping {context_type} {id_context} in file {file_basename} due to invalid score format: {score_str}")
            return None, None
    def run_analysis(self):
        if not self.file_paths:
            messagebox.showerror("No Files", "Please load at least one .OUT file.")
            return

        try:
            user_min_score = self.min_score.get()
            user_max_score = self.max_score.get()
        except tk.TclError:
            messagebox.showerror("Input Error", "Please enter valid numbers for Min Score and Max Score.")
            return

        all_species_raw = []
        all_consensus_metadata = []
        all_species_represented = []
        consensus_area_lines = []

        self.update_summary("Starting analysis...\n")

        for path in self.file_paths:
            self.update_summary(f"Processing: {os.path.basename(path)}\n", append=True)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception as e:
                messagebox.showerror("File Error", f"Could not read {os.path.basename(path)}: {e}")
                continue

            file_basename = os.path.basename(path)
            grid_match = re.search(r'(\d+(?:[.,]\d+)?)', file_basename)
            grid_size = grid_match.group(1).replace(',', '.') if grid_match else 'N/A'

            # --- Species represented ---
            species_represented = self.extract_species_represented(text)
            for species in species_represented:
                if not species.startswith("GRP-") or self.include_grp.get():
                    all_species_represented.append({
                        'Grid Size': grid_size,
                        'File': file_basename,
                        'Species Represented': species
                    })

            # --- Individual Areas ---
            area_blocks = re.finditer(r"(AREA\s+(\d+):.*?Score = (\d\.\d+|\(\d\.\d+-\d\.\d+\)).*?Species:(.*?)(?=\n\nAREA\s+\d+:|\Z))", text, re.DOTALL)
            for match_area in area_blocks:
                _, area_id, score_str, species_block = match_area.groups()
                species_list = re.findall(r"\*?\s*(\S.+?)\n", species_block)
                min_s, max_s = self._parse_score_string(score_str, area_id, file_basename, "Area")
                if min_s is None:
                    continue
                for species in species_list:
                    all_species_raw.append({
                        'ID': area_id,
                        'Species': species.strip(),
                        'Score Min': min_s,
                        'Score Max': max_s,
                        'Source Type': 'Individual Area',
                        'File': file_basename
                    })
                                
            # --- Consensus Areas (SET NR.) ---
            set_blocks = re.finditer(
                r"(SET NR\.\s*(\d+).*?score\s*([\d\.]+)\s*\n"
                r"(?:Comprising area.*?\n)?"
                r"\s*\d+\s*scoring\s*spp\.\s*\(sp/score\):\s*\n"
                r")(.*?)(?=\nSET NR\.|\Z)",
                text,
                re.DOTALL
            )

            for match_set in set_blocks:
                header, set_id, set_score_str, species_block = match_set.groups()

                # Score in sets
                try:
                    set_score = float(set_score_str)
                except (TypeError, ValueError):
                    set_score = None

                # Areas included
                comprising = re.search(r"Comprising area\s*([\d,\s]+)", header)
                areas = [a.strip() for a in comprising.group(1).split(',')] if comprising else []

                # Extract "size N" from the "SET NR. X, size N, score S" line
                size_match = re.search(r"size\s+(\d+)", header)
                area_size = int(size_match.group(1)) if size_match else None

                # Save SET metadata
                all_consensus_metadata.append({
                    'Set ID': set_id,
                    'Set Score': set_score,
                    'Area Size': area_size,
                    'Comprising Areas': areas,
                    'File': file_basename
                })

                # Extract species and their scores within this SET
                matches = re.findall(
                    r"^\s*\d+\s*([\w\s._-]+?)\s*(?:\(\d+\))?:\s*"
                    r"(\(\d+\.\d+-\d+\.\d+\)|\d+\.\d+)",
                    species_block,
                    re.MULTILINE
                )
                for name, score_str in matches:
                    min_s, max_s = self._parse_score_string(
                        score_str, name, file_basename, f"Set {set_id}"
                    )
                    if min_s is None:
                        continue
                    all_species_raw.append({
                        'ID': set_id,
                        'Species': name.strip(),
                        'Score Min': min_s,
                        'Score Max': max_s,
                        'Source Type': 'Consensus Area',
                        'File': file_basename
                    })

            # --- Consensus area (X from Y areas) ---
            matches = re.finditer(r"Consensus area\s+(\d+)\s+\(from\s+(\d+)\s+areas?\)", text)
            for match in matches:
                consensus_id, num_areas = match.groups()
                consensus_area_lines.append({
                    'Set ID': int(consensus_id),
                    'Included Area Count': int(num_areas),
                    'File': file_basename
                })
                     
        # Create DataFrames
        df_raw = pd.DataFrame(all_species_raw)
        df_represented = pd.DataFrame(all_species_represented)
        df_consensus = pd.DataFrame(all_consensus_metadata)
        df_area_count = pd.DataFrame(consensus_area_lines)

        if df_raw.empty:
            messagebox.showinfo("No Results", "No endemic species found in any file.")
            self.update_summary("No species found in any input file.")
            return

        # Filters
        df_filtered = df_raw.copy()
        if not self.include_grp.get():
            df_filtered = df_filtered[~df_filtered['Species'].str.startswith("GRP-")]
        df_filtered = df_filtered[(df_filtered['Score Max'] >= user_min_score) & (df_filtered['Score Min'] <= user_max_score)]
                
        try:
            species_count = df_represented['Species Represented'].nunique()
        except (KeyError, AttributeError):
            species_count = 0

        # Global totals for individual and consensus areas
        total_individual_areas = pd.DataFrame(all_consensus_metadata)[['File', 'Set ID']].drop_duplicates().shape[0]

        # Each row in df_area_count represents one "Consensus area X" per file
        if not df_area_count.empty:
            total_consensus_sets = df_area_count[['File', 'Set ID']].drop_duplicates().shape[0]
        else:
            total_consensus_sets = 0

        # Table 1: Summary
        df1_summary = pd.DataFrame({
            'Metric': [
                'Total Files Processed',
                'Total Records Exported (filtered)',
                'Total Unique Species Exported (filtered)',
                'Total Individual Areas Found (raw)',
                'Total Consensus Sets Found (raw)'
                
            ],
            'Value': [
                len(self.file_paths),
                len(df_filtered),
                df_filtered['Species'].nunique(),
                total_individual_areas,
                total_consensus_sets                
            ]
        })

        # Table 2: Individual Endemism Areas (SET NR.) + filtered unique species count
        species_map = self.build_species_map_fixed(self.file_paths, user_min_score, user_max_score, self.include_grp.get())

        df2_consensus = pd.DataFrame(all_consensus_metadata)
        df2_consensus['Set ID'] = df2_consensus['Set ID'].astype(int)  
                
        if 'Comprising Areas' in df2_consensus.columns:
            df2_consensus.drop(columns=['Comprising Areas'], inplace=True)

        count_records = []
        for row in all_consensus_metadata:
            sid = int(row['Set ID'])
            f = row['File']
            filtered_species = species_map.get((f, sid), [])
            unique_species = set(name for name, score in filtered_species)
            count_records.append({'Set ID': sid, 'File': f, 'Filtered Unique Species Count': len(unique_species)})

        df_counts = pd.DataFrame(count_records)
        df_counts['Set ID'] = df_counts['Set ID'].astype(int)  # Asegura tipo entero

        df2_consensus = pd.merge(df2_consensus, df_counts, on=['Set ID', 'File'], how='left')
        df2_consensus['Filtered Unique Species Count'] = df2_consensus['Filtered Unique Species Count'].fillna(0).astype(int)

        # Table 3: Consensus areas
        df3_areas = df_area_count
                
        # Table 4: Individual Endemism Area summary per SET NR. (raw vs filtered, min/max, genera, etc.)
        
        individual_records = []
        high_threshold = 0.9  # Threshold for N_HighScore_Species

        for meta in all_consensus_metadata:
            set_id = str(meta['Set ID'])
            file_basename = meta['File']
            set_score = meta.get('Set Score', None)
            area_size = meta.get('Area Size', None)

            # Extract Grid Size from filename (e.g., 2.5.out, 10.out)
            grid_match = re.search(r'(\d+(?:[.,]\d+)?)', file_basename)
            grid_size = grid_match.group(1).replace(',', '.') if grid_match else 'N/A'

            # Use ONLY species where Source Type = 'Consensus Area'
            mask_raw = (
                (df_raw['File'] == file_basename) &
                (df_raw['ID'].astype(str) == set_id) &
                (df_raw['Source Type'] == 'Consensus Area')
            )
            mask_filt = (
                (df_filtered['File'] == file_basename) &
                (df_filtered['ID'].astype(str) == set_id) &
                (df_filtered['Source Type'] == 'Consensus Area')
            )

            sub_raw = df_raw[mask_raw]
            sub_f = df_filtered[mask_filt]

            # Number of raw and filtered species in this SET
            n_raw = sub_raw['Species'].nunique()
            n_filt = sub_f['Species'].nunique()

            if not sub_f.empty:
                score_min_f = sub_f['Score Min'].min()
                score_max_f = sub_f['Score Max'].max()

                # High-score species (Max Score >= threshold)
                n_high = sub_f[sub_f['Score Max'] >= high_threshold]['Species'].nunique()

                # Number of genera among filtered species
                genera = sub_f['Species'].dropna().astype(str).apply(lambda s: s.split('_')[0])
                n_genera = genera.nunique()
            else:
                score_min_f = None
                score_max_f = None
                n_high = 0
                n_genera = 0

            individual_records.append({
                'File': file_basename,
                'Grid Size': grid_size,
                'Area Type': 'Individual Area',   
                'Set ID': set_id,
                'Set Score': set_score,
                'Area Size (cells)': area_size,
                'N_Species_Raw_in_Set': n_raw,
                'N_Species_Filtered_in_Set': n_filt,
                'Score_Min_Filtered': score_min_f,
                'Score_Max_Filtered': score_max_f,
                'N_HighScore_Species': n_high,
                'N_Genera_Filtered': n_genera
            })

        df4_individual = pd.DataFrame(individual_records)
                
        detail_records = []
        for (fname, sid), entries in species_map.items():
            for species_name, score in entries:
                detail_records.append({
                    'Set ID': sid,
                    'Species': species_name,
                    'Score Min': score,
                    'Score Max': score,   
                    'File': fname
                })

        df4_species = pd.DataFrame(detail_records)

        # Table 5: Filtered species records
        def extract_grid_size(filename):
            match = re.search(r'(\d+(?:[.,]\d+)?)', filename)
            return match.group(1).replace(',', '.') if match else 'N/A'

        df5 = df_filtered.copy()
        df5['Grid Size'] = df5['File'].apply(extract_grid_size)
        df5.rename(columns={'ID': 'Area/Set ID'}, inplace=True)
        df5 = df5[['Species', 'Grid Size', 'Area/Set ID', 'Score Min', 'Score Max', 'Source Type', 'File']]
                
        # Table 6: Species count by Genus per (File, Grid-Resolution, Area/Set ID) using filtered records 
        
        df5_copy = df5.copy()

        # Extract genera  
        df5_copy['Genus'] = df5_copy['Species'].apply(lambda x: x.split('_')[0])               
        if 'Source Type' in df5_copy.columns:
            df5_copy.drop(columns=['Source Type'], inplace=True)
        
        df6_genus = (
            df5_copy.groupby(
                ['File', 'Grid Size', 'Area/Set ID', 'Genus']
            )['Species']
            .nunique()
            .reset_index()
            .rename(columns={'Species': 'N_Species'})
        )
                
        consensus_species_records = []

        for path in self.file_paths:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            file_basename = os.path.basename(path)

            # Grid Size: spatial resolution derived from filename (2.5, 5, 10, 12.5, etc.)
            grid_match = re.search(r'(\d+(?:[.,]\d+)?)', file_basename)
            grid_size = grid_match.group(1).replace(',', '.') if grid_match else 'N/A'
                        
            cons_section_match = re.search(
                r"-{3,}\s*INFORMATION ON CONSENSUS AREAS\s*-{3,}(.*?)(?=\n-{3,}|$)",
                content,
                re.DOTALL
            )
            if not cons_section_match:
                continue

            cons_block = cons_section_match.group(1)

            # Each "Consensus area X (from Y areas), N species give score:" header
            consensus_pattern = (
                r"Consensus area\s+(\d+)\s+\(from\s+(\d+)\s+areas?\),\s*"
                r"\d+\s+species\s+give\s+score:\s*(.*?)(?=\n\s*Consensus area\s+\d+\s+\(from|\Z)"
            )

            for cons_match in re.finditer(consensus_pattern, cons_block, re.DOTALL):
                cons_id_str, n_areas_str, species_block = cons_match.groups()
                cons_id = int(cons_id_str)
                n_areas = int(n_areas_str)

                # Loop through species in the current consensus block
                for line in species_block.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    # Typical format: "50 Aedes_annulirostris (50): (0.711)" or "(0.000-0.765)"
                    m = re.match(
                        r"\d+\s+([A-Za-z0-9_.-]+)\s*\(\d+\):\s*\(([\d\.]+(?:-[\d\.]+)?)\)",
                        line
                    )
                    if not m:
                        continue

                    species_name, score_str = m.groups()

                    # Respect the option to exclude 'GRP-' if selected by the user
                    if (not self.include_grp.get()) and species_name.startswith("GRP-"):
                        continue

                    # Score Min / Max
                    if '-' in score_str:
                        s_min_str, s_max_str = score_str.split('-', 1)
                        s_min = float(s_min_str)
                        s_max = float(s_max_str)
                    else:
                        s_min = s_max = float(score_str)

                    # Filter by user-defined score range
                    if s_max < user_min_score or s_min > user_max_score:
                        continue

                    consensus_species_records.append({
                        'Species': species_name.strip(),
                        'Grid Size': grid_size,                   
                        'Consensus Area/Set ID': cons_id,         
                        'Score Min': s_min,
                        'Score Max': s_max,
                        'Individual areas included': n_areas,     
                        'File': file_basename
                    })
        
        df6_consensus_species = pd.DataFrame(consensus_species_records)
                
        df_consensus = pd.DataFrame(all_consensus_metadata)
                
        count_records = []
        for row in all_consensus_metadata:
            sid = row['Set ID']
            f = row['File']
            species_entries = species_map.get((f, sid), [])
            species_names = [entry[0] for entry in species_entries]  
            count = len(set(species_names))  
            count_records.append({'Set ID': sid, 'File': f, 'Filtered Unique Species Count': count})
                
        endemic_species_records = []

        for path in self.file_paths:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            file_basename = os.path.basename(path)
            grid_match = re.search(r'(\d+[,\.]\d+)', file_basename)
            grid_size = grid_match.group(1).replace(',', '.') if grid_match else 'N/A'
                        
            endemic_section_match = re.search(r"-{3,}\s*INFORMATION ON ENDEMIC SPECIES\s*-{3,}(.*?)(?=\n-{3,}|$)", content, re.DOTALL)
            if not endemic_section_match:
                continue
            endemic_block = endemic_section_match.group(1).strip()
                        
            species_blocks = re.split(r"\n\s*Sp\.\s*\d+\s+", endemic_block)
            species_headers = re.findall(r"\n\s*Sp\.\s*(\d+)\s+([^\n]+)", endemic_block)

            for i, (sp_number, header_line) in enumerate(species_headers):
                if i >= len(species_blocks):
                    continue
                sp_block = species_blocks[i + 1] if i + 1 < len(species_blocks) else ''
                header_parts = re.match(r"([^\(]+)\s+\((\d+)\s+records\)", header_line.strip())
                if not header_parts:
                    continue
                sp_name = header_parts.group(1).strip()
                n_records = int(header_parts.group(2))

                scores_found = re.findall(r"(\d+):\s+([\d\.]+)", sp_block)
                valid_scores = [(int(set_id), float(score)) for set_id, score in scores_found
                                if user_min_score <= float(score) <= user_max_score]

                if valid_scores:
                    endemic_species_records.append({
                        'Species Number': int(sp_number),
                        'Species Name': sp_name,
                        'Records': n_records,
                        'Endemic in Sets': ', '.join(str(sid) for sid, _ in valid_scores),
                        'Scores in Range': '; '.join(f"{sid}: {score:.6f}" for sid, score in valid_scores),
                        'File': file_basename,
                        'Grid Size': grid_size
                    })

        # Table 7: Endemic Species info (from "INFORMATION ON ENDEMIC SPECIES") filtered by user score range

        df6_endemics = pd.DataFrame(endemic_species_records)

        # Table 8: Data stats
        performance_records = []
                
        def extract_grid_size(filename):
            match = re.search(r'(\d+(?:[.,]\d+)?)', filename)
            return match.group(1).replace(',', '.') if match else 'N/A'
                
        files_in_raw = sorted(df_raw['File'].unique())

        for fname in files_in_raw:
            grid = extract_grid_size(fname)

            sub_raw = df_raw[df_raw['File'] == fname]
            sub_filt = df_filtered[df_filtered['File'] == fname]
                        
            sub_indiv = df2_consensus[df2_consensus['File'] == fname]
            n_indiv = sub_indiv['Set ID'].nunique()
                        
            sub_cons = df3_areas[df3_areas['File'] == fname]
            n_cons = sub_cons['Set ID'].nunique()

            n_spp_raw = sub_raw['Species'].nunique()
            n_spp_filt = sub_filt['Species'].nunique()

            performance_records.append({
                'File': fname,
                'Grid Size': grid,
                'N_Individual_Areas': n_indiv,
                'N_Consensus_Sets': n_cons,
                'N_Species_Raw': n_spp_raw,
                'N_Species_Filtered': n_spp_filt
            })

        df7_performance = pd.DataFrame(performance_records)

        # Export to Excel
        output_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")]
        )

        if output_path:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                                
                df1_summary.to_excel(writer, sheet_name='1_Summary_General', index=False)
                                
                df2_consensus.to_excel(writer, sheet_name='2_Individual_EAreas', index=False)
                                
                df3_areas.to_excel(writer, sheet_name='3_Consensus_EAreas', index=False)
                                
                df4_species.to_excel(writer, sheet_name='4_Spp_Detail_EAreas', index=False)
                                
                df6_consensus_species.to_excel(writer, sheet_name='5_Spp_Detail_Consensus_EAreas', index=False)
                                
                df6_genus.to_excel(writer, sheet_name='6_Spp_by_Genus_EAreas', index=False)
                                
                df6_endemics.to_excel(writer, sheet_name='7_Consensus_Endemic_Spp_Info', index=False)
                               
                df7_performance.to_excel(writer, sheet_name='8_Data_Stats', index=False)

            messagebox.showinfo("Done", f"Analysis complete. File saved as:\n{output_path}")

        else:
            messagebox.showwarning("Export Cancelled", "Excel file export was cancelled.")

    def _read_polygon_from_con_csv(self, poly_path):
        """Read a conX_N.csv and return a shapely geometry (Polygon/MultiPolygon)."""
        from shapely import wkt
        from shapely.ops import unary_union
        from shapely.geometry import Polygon

        try:
            df_poly = pd.read_csv(poly_path)
        except Exception as e:
            raise RuntimeError(f"Error reading polygon CSV: {e}")

        # Case 1: WKT column
        wkt_col = None
        for col in df_poly.columns:
            if col.strip().upper() == "WKT":
                wkt_col = col
                break

        if wkt_col is not None:
            geoms = df_poly[wkt_col].dropna().astype(str).apply(wkt.loads)
            if geoms.empty:
                raise RuntimeError("No valid WKT geometries.")
            return unary_union(list(geoms))

        # Case 2: lon/lat columns
        lon_col = None
        lat_col = None
        for col in df_poly.columns:
            c = col.strip().lower()
            if c in ("lon", "long", "longitude", "x"):
                lon_col = col
            elif c in ("lat", "latitude", "y"):
                lat_col = col

        if lon_col is None or lat_col is None:
            raise RuntimeError(f"No WKT or lon/lat columns found. Columns={list(df_poly.columns)}")

        try:
            return Polygon(zip(df_poly[lon_col], df_poly[lat_col]))
        except Exception as e:
            raise RuntimeError(f"Error building polygon from lon/lat: {e}")

    def _plot_shapely_geom_edges(self, ax, geom, edgecolor=None, linewidth=0.8):
        """Plot only edges of Polygon/MultiPolygon geometry."""
        if geom is None:
            return

        gtype = getattr(geom, "geom_type", "")
        if gtype == "Polygon":
            x, y = geom.exterior.xy
            ax.plot(x, y, linewidth=linewidth, color=edgecolor)
        elif gtype == "MultiPolygon":
            for g in geom.geoms:
                x, y = g.exterior.xy
                ax.plot(x, y, linewidth=linewidth, color=edgecolor)
        else:
            # GeometryCollection or others
            if hasattr(geom, "geoms"):
                for g in geom.geoms:
                    self._plot_shapely_geom_edges(ax, g, edgecolor=edgecolor, linewidth=linewidth)

    def plot_consensus_mosaic(self):
        """
        Simple mosaic.
        - User selects a root folder containing treatment subfolders
        - Program finds conX_N.csv files
        - Builds shapely geometries
        - Exports a PNG mosaic (rows/cols)
        """      
        
        # Import matplotlib lazily
        try:
            import matplotlib.pyplot as plt
            from matplotlib.ticker import MaxNLocator
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "This feature requires matplotlib.\nInstall it with:\n\npip install matplotlib"
            )
            return

        # Select folder root
        folder_root = filedialog.askdirectory(
            title="Select root folder containing treatment subfolders (any names)"
        )
        if not folder_root:
            return

        self.update_summary(f"\n[MOSAIC] Selected root folder:\n{folder_root}\n", append=True)

        # -------------------------------------------------
        # OPTIONAL BASEMAP (user can cancel)
        # -------------------------------------------------
        basemap_gdf = None
        basemap_path = filedialog.askopenfilename(
            title="(Optional) Select basemap file (.shp or .gpkg) - Cancel to skip",
            filetypes=[("Vector files", "*.shp *.gpkg"), ("All files", "*.*")]
        )

        if basemap_path:
            try:
                if basemap_path.lower().endswith(".gpkg"):
                    # Choose the first layer with valid geometry
                    layers = gpd.list_layers(basemap_path)
                    basemap_gdf = None
                    for lyr in layers["name"]:
                        tmp = gpd.read_file(basemap_path, layer=lyr)
                        if tmp is not None and not tmp.empty and tmp.geometry.notna().any():
                            basemap_gdf = tmp
                            self.update_summary(f"[MOSAIC] Using GPKG layer: {lyr}\n", append=True)
                            break
                    if basemap_gdf is None:
                        raise RuntimeError("No valid geometry layer found in the GeoPackage.")
                else:
                    basemap_gdf = gpd.read_file(basemap_path)

                # Ensure a CRS exists; assume EPSG:4326 if missing
                if basemap_gdf.crs is None:
                    basemap_gdf = basemap_gdf.set_crs(epsg=4326)

            except Exception as e:
                basemap_gdf = None
                self.update_summary(f"[MOSAIC] Basemap could not be loaded: {e}\n", append=True)

        # Detect subfolders (treatments)
        grid_folders = []
        for item in os.listdir(folder_root):
            p = os.path.join(folder_root, item)
            if os.path.isdir(p):
                label = item.strip()
                if label:
                    grid_folders.append((label, p))

        # Sort numeric-like labels first
        def _folder_sort_key(t):
            label = t[0].replace(",", ".")
            try:
                return (0, float(label))
            except ValueError:
                return (1, label.lower())

        grid_folders.sort(key=_folder_sort_key)

        if not grid_folders:
            messagebox.showwarning("No subfolders found", "No treatment subfolders were found.")
            return

        pattern_con = re.compile(r"^con(\d+)_(\d+)\.csv$", re.IGNORECASE)

        # Collect geometries
        items = []  # list of dicts: {treatment,label,cid,total,path,geom}
        for treatment, tdir in grid_folders:
            try:
                fnames = os.listdir(tdir)
            except Exception as e:
                self.update_summary(f"[MOSAIC] ERROR listing {tdir}: {e}\n", append=True)
                continue

            for fname in fnames:
                m = pattern_con.match(fname)
                if not m:
                    continue
                cid = int(m.group(1))
                total = int(m.group(2))
                poly_path = os.path.join(tdir, fname)

                try:
                    geom = self._read_polygon_from_con_csv(poly_path)
                except Exception as e:
                    self.update_summary(f"[MOSAIC] Skipping {fname} ({treatment}): {e}\n", append=True)
                    continue

                items.append({
                    "treatment": treatment,
                    "cid": cid,
                    "total": total,
                    "path": poly_path,
                    "geom": geom
                })

        if not items:
            messagebox.showwarning("No consensus files", "No valid conX_N.csv polygons were found.")
            return

        # Global bounds (same extent for all panels)
        bounds = []
        for it in items:
            try:
                b = it["geom"].bounds  # (minx,miny,maxx,maxy)
                bounds.append(b)
            except Exception:
                pass

        if bounds:
            minx = min(b[0] for b in bounds)
            miny = min(b[1] for b in bounds)
            maxx = max(b[2] for b in bounds)
            maxy = max(b[3] for b in bounds)
        else:
            minx = miny = 0.0
            maxx = maxy = 1.0

        # Layout
        n = len(items)
        ncols = math.ceil(math.sqrt(n))
        nrows = math.ceil(n / ncols)

        # Keep figure size reasonable
        cell = 3.0  # inches per panel
        figw = min(30.0, ncols * cell)
        figh = min(30.0, nrows * cell)

        fig, axes = plt.subplots(nrows, ncols, figsize=(figw, figh))
        if nrows * ncols == 1:
            axes = [axes]
        else:
            axes = axes.flatten()

        # Color by treatment
        treatments = sorted({it["treatment"] for it in items}, key=lambda s: _folder_sort_key((s, "")))
        color_map = {t: None for t in treatments}  # matplotlib assigns default if None; but we’ll set explicit cycle index
        # Use matplotlib default color cycle
        default_colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
        for i, t in enumerate(treatments):
            if default_colors:
                color_map[t] = default_colors[i % len(default_colors)]
            else:
                color_map[t] = None
                
        # Plot each item
        for ax, it in zip(axes, items):
            t = it["treatment"]
            cid = it["cid"]
            total = it["total"]
            title = f"{t} | con{cid}_{total}"

            ax.set_title(title, fontsize=8)

            # (FIX) Plot basemap per-axes (ax exists here)
            if basemap_gdf is not None and not basemap_gdf.empty:
                try:
                    basemap_gdf.boundary.plot(
                    ax=ax,
                    color="#666666",     
                    linewidth=0.5,
                    alpha=0.5
                )
                except Exception as e:
                    # optional:
                    # self.update_summary(f"[MOSAIC] Basemap plot failed: {e}\n", append=True)
                    pass

            # Plot consensus geometry on top
            self._plot_shapely_geom_edges(ax, it["geom"], edgecolor=color_map.get(t), linewidth=1.5)

            ax.set_xlim(minx, maxx)
            ax.set_ylim(miny, maxy)
            ax.set_aspect("equal", adjustable="box")

            ax.xaxis.set_major_locator(MaxNLocator(4))
            ax.yaxis.set_major_locator(MaxNLocator(4))
            ax.grid(True, linewidth=0.5, linestyle="--", alpha=0.5)

        # Turn off unused axes
        for k in range(len(items), len(axes)):
            axes[k].axis("off")

        plt.tight_layout()

        # Save PNG
        out_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            title="Save mosaic PNG"
        )
        if not out_path:
            plt.close(fig)
            return

        try:
            fig.savefig(out_path, dpi=300, bbox_inches="tight")
            plt.close(fig)
            messagebox.showinfo("Done", f"Mosaic saved as:\n{out_path}")
            self.update_summary(f"[MOSAIC] Saved PNG:\n{out_path}\n", append=True)
        except Exception as e:
            plt.close(fig)
            messagebox.showerror("Save Error", f"Could not save PNG:\n{e}")

if __name__ == '__main__':
    root = None
    try:
        root = tk.Tk()
        app = NDMOutAnalyzer(root)
        root.mainloop()
    except Exception as e:
        if root:
            messagebox.showerror("Critic error", f"An unexpected error has occurred:\n{e}")
        else:
            print(f"Critical error before full Tkinter initialization: {e}")
        traceback.print_exc()

