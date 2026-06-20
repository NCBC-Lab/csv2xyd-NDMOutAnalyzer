import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import dask.dataframe as dd
import time
import os
from fuzzywuzzy import fuzz
import folium
import webbrowser
import tempfile
import geopandas as gpd
from shapely.geometry import Point, Polygon
import numpy as np

class CSVProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("csv2xyd")

        # Add a Canvas for the continent design
        self.canvas = tk.Canvas(root, width=300, height=150, bg="white")
        self.canvas.pack(pady=10)
        self.draw_minimalist_south_america(self.canvas)
        self.canvas.create_text(230, 100, text="csv ⮕ xyd", font=("Arial", 18), fill="black")

        # Configuration parameters for nufile.xyd
        self.grid_x = tk.StringVar(value="-180")
        self.grid_y = tk.StringVar(value="70")
        self.fill_value = tk.StringVar(value="25")
        self.assume_value = tk.StringVar(value="100")

        # Configuration parameter to remove species with few occurrences
        self.min_occurrences = tk.IntVar(value=10)

        # Configuration parameter for similarity threshold
        self.similarity_threshold = tk.IntVar(value=90)

        # Main menu
        self.menu = tk.Menu(root)
        root.config(menu=self.menu)

        # File Menu
        self.file_menu = tk.Menu(self.menu, tearoff=0)
        self.file_menu.add_command(label="Open CSV", command=self.open_csv)
        self.file_menu.add_command(label="Import CSV from Biodiversity Repository", command=self.process_large_csv_with_dask)
        self.file_menu.add_command(label="Merge and Sort CSVs", command=self.merge_and_sort_csvs)
        self.file_menu.add_command(label="Reorder Columns", command=self.reorder_columns)  # Nueva opción de reordenar columnas
        self.file_menu.add_command(label="Exit", command=root.quit)
        self.menu.add_cascade(label="File", menu=self.file_menu)

        # Preprocessing Menu
        self.preprocess_menu = tk.Menu(self.menu, tearoff=0)
        self.preprocess_menu.add_command(label="Remove Duplicates", command=self.preprocess_duplicates)
        self.preprocess_menu.add_command(label="Configure Occurrence Filter", command=self.configure_occurrences)
        self.preprocess_menu.add_command(label="Configure Similarity Threshold", command=self.configure_similarity_threshold)
        self.preprocess_menu.add_command(label="Detect Typographical Errors", command=self.detect_typo_errors)
        self.preprocess_menu.add_command(label="Load Corrections from CSV", command=self.load_corrections_from_csv)
        self.preprocess_menu.add_command(label="Show Occurrence Map", command=self.show_occurrence_map)
        self.preprocess_menu.add_command(label="Detect Taxonomic Errors", command=self.detect_taxonomic_errors)
        self.menu.add_cascade(label="Preprocessing", menu=self.preprocess_menu)

        # Processing Menu
        self.process_menu = tk.Menu(self.menu, tearoff=0)
        self.process_menu.add_command(label="Select Columns", command=self.create_column_checkbuttons, state=tk.DISABLED)
        self.process_menu.add_command(label="Configure nufile.xyd", command=self.configure_nufile)
        self.process_menu.add_command(label="Process CSV", command=self.process_csv)
        self.menu.add_cascade(label="Processing", menu=self.process_menu)
        
        # Add Geospatial Analysis Menu
        self.geospatial_menu = tk.Menu(self.menu, tearoff=0)
        self.geospatial_menu.add_command(label="Run Geospatial Analysis", command=self.run_geospatial_analysis)
        self.menu.add_cascade(label="Geospatial Analysis", menu=self.geospatial_menu)
        
        # NDM / vNDM Output Analysis Menu
        self.ndm_menu = tk.Menu(self.menu, tearoff=0)
        self.ndm_menu.add_command(
            label="Analyze NDM/vNDM Output (.out)",
            command=self.launch_ndm_out_analyzer
        )
        self.menu.add_cascade(label="Out NDM/vNDM", menu=self.ndm_menu)
        
        # About Menu
        self.about_menu = tk.Menu(self.menu, tearoff=0)
        self.about_menu.add_command(label="About", command=self.show_about)
        self.menu.add_cascade(label="About", menu=self.about_menu)
        
        self.label = tk.Label(root, text="Select a CSV file to process")
        self.label.pack(pady=10)
        
        self.open_button = tk.Button(root, text="Open CSV", command=self.open_csv)
        self.open_button.pack(pady=5)

        self.show_map_button = tk.Button(root, text="Show Occurrence Map", command=self.show_occurrence_map, state=tk.DISABLED)
        self.show_map_button.pack(pady=5)

        self.csv_data = None
        self.current_csv_path = None
        self.columns_frame = None
        self.column_vars = {}
        self.typographic_errors = []              

    def draw_minimalist_south_america(self, canvas):
        # Logo design continent and endemism area
        square_size = 18
        positions = [
            (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), 
            (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1),
            (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
            (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
            (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), 
            (1, 5), (2, 5), (3, 5), 
            (2, 6), (3, 6)
        ]
        red_positions = [
            (2, 2), (3, 2), (2, 3), (3, 3)
        ]
        for x, y in positions:
            color = "red" if (x, y) in red_positions else "green"
            canvas.create_rectangle(
                x * square_size, y * square_size, (x + 1) * square_size, (y + 1) * square_size,
                fill=color, outline="black"
            )

    def open_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv;*.tsv")])
        if file_path:
            self.current_csv_path = file_path
            try:
                delimiter = self.ask_delimiter()
                self.csv_data = pd.read_csv(file_path, sep=delimiter, dtype=str, low_memory=False)
                
                required_columns = {'latitude', 'longitude', 'species'}
                if not required_columns.issubset(self.csv_data.columns):
                    raise ValueError(f"The CSV file must contain the columns: {', '.join(required_columns)}")

                total_occurrences = len(self.csv_data)
                estimated_memory = self.csv_data.memory_usage(deep=True).sum() / (1024 ** 2)  # Convert to MB

                messagebox.showinfo("File Loaded", f"The CSV file has been loaded successfully.\nTotal occurrences: {total_occurrences}\nEstimated RAM required: {estimated_memory:.2f} MB")
                self.show_map_button.config(state=tk.NORMAL)
                self.process_menu.entryconfig("Select Columns", state=tk.DISABLED)  # Disable column selection until occurrences are configured
            except Exception as e:
                messagebox.showerror("Error", f"Could not load the CSV file: {e}")

    def preprocess_duplicates(self):
        if self.csv_data is not None:
            initial_count = len(self.csv_data)
            self.csv_data = self.csv_data.drop_duplicates(subset=['species', 'longitude', 'latitude'])
            final_count = len(self.csv_data)
            duplicates_removed = initial_count - final_count

            if duplicates_removed > 0:
                messagebox.showinfo("Preprocessing Complete", f"Duplicates successfully removed. {duplicates_removed} duplicates were removed.")
            else:
                messagebox.showinfo("Preprocessing Complete", "No duplicates found.")
        else:
            messagebox.showwarning("Warning", "Load a CSV file before preprocessing.")
    
    def create_column_checkbuttons(self):
        if self.csv_data is None:
            messagebox.showwarning("Warning", "Load a CSV file before selecting columns.")
            return
        
        if self.columns_frame:
            self.columns_frame.destroy()
        
        self.columns_frame = tk.Frame(self.root)
        self.columns_frame.pack(pady=10)
        
        tk.Label(self.columns_frame, text="Select the columns to include in output.tnt:").pack(pady=5)
        
        # Check columns are in the correct order
        column_order = ['phylum', 'class', 'order', 'family', 'genus', 'species']
        for col in column_order:
            if col in self.csv_data.columns:
                var = tk.BooleanVar(value=col in ['genus', 'species'])
                chk = tk.Checkbutton(self.columns_frame, text=col, variable=var, state=tk.DISABLED if col in ['genus', 'species'] else tk.NORMAL)
                chk.pack(anchor='w')
                self.column_vars[col] = var
    
    def configure_nufile(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("nufile.xyd Configuration")

        tk.Label(config_window, text="gridx").grid(row=0, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.grid_x).grid(row=0, column=1, padx=10, pady=5)

        tk.Label(config_window, text="gridy").grid(row=1, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.grid_y).grid(row=1, column=1, padx=10, pady=5)

        tk.Label(config_window, text="fill").grid(row=2, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.fill_value).grid(row=2, column=1, padx=10, pady=5)

        tk.Label(config_window, text="assume").grid(row=3, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.assume_value).grid(row=3, column=1, padx=10, pady=5)

        tk.Button(config_window, text="Save", command=config_window.destroy).grid(row=4, column=0, columnspan=2, pady=10)

    def configure_occurrences(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configure Occurrence Filter")

        tk.Label(config_window, text="Minimum number of occurrences:").grid(row=0, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.min_occurrences).grid(row=0, column=1, padx=10, pady=5)

        def save_config():
            config_window.destroy()
            self.process_menu.entryconfig("Select Columns", state=tk.NORMAL)  # Enable column selection after occurrences are configured
        
        tk.Button(config_window, text="Save", command=save_config).grid(row=1, column=0, columnspan=2, pady=10)

    def configure_similarity_threshold(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configure Similarity Threshold")

        tk.Label(config_window, text="Similarity threshold (%):").grid(row=0, column=0, padx=10, pady=5)
        tk.Entry(config_window, textvariable=self.similarity_threshold).grid(row=0, column=1, padx=10, pady=5)

        tk.Button(config_window, text="Save", command=config_window.destroy).grid(row=1, column=0, columnspan=2, pady=10)
    
    def detect_typo_errors(self):
        if self.csv_data is None:
            messagebox.showwarning("Warning", "Load a CSV file before detecting typographical errors.")
            return

        species = self.csv_data['species'].unique()
        possible_typos = []

        threshold = self.similarity_threshold.get()

        for species1 in species:
            for species2 in species:
                if species1 != species2 and fuzz.ratio(species1, species2) > threshold:  # similarity threshold
                    species1_count = len(self.csv_data[self.csv_data['species'] == species1])
                    species2_count = len(self.csv_data[self.csv_data['species'] == species2])
                    suggested_correction = species1 if species1_count >= species2_count else species2
                    possible_typos.append((species1, species2, species1_count, species2_count, suggested_correction))

        self.typographic_errors = possible_typos

        # Generate file of possible typographical errors
        with open("possible_typo_errors.csv", "w") as f:
            f.write("species1,species2,species1_count,species2_count,suggested_correction\n")
            for typo in possible_typos:
                f.write(f"{typo[0]},{typo[1]},{typo[2]},{typo[3]},{typo[4]}\n")
        
        messagebox.showinfo("Detection Complete", "A file 'possible_typo_errors.csv' with possible typographical errors has been generated.")

    def detect_taxonomic_errors(self):
        if self.csv_data is None:
            messagebox.showwarning("Warning", "Load a CSV file before detecting taxonomic errors.")
            return

        required_columns = ['phylum', 'class', 'order', 'family', 'genus', 'species']
        if not all(column in self.csv_data.columns for column in required_columns):
            messagebox.showerror("Error", "The CSV file must contain the columns: phylum, class, order, family, genus, species.")
            return

        inconsistencies = []

        grouped = self.csv_data.groupby('species')
        for species, group in grouped:
            for column in required_columns[:-1]:  # Exclude 'species'
                unique_values = group[column].unique()
                if len(unique_values) > 1:
                    inconsistencies.append({
                        'species': species,
                        'column': column,
                        'unique_values': unique_values
                    })

        if inconsistencies:
            inconsistencies_df = pd.DataFrame(inconsistencies)
            inconsistencies_df.to_csv('taxonomic_inconsistencies.csv', index=False)
            messagebox.showinfo("Detection Complete", "Taxonomic inconsistencies found. See 'taxonomic_inconsistencies.csv' for more details.")
        else:
            messagebox.showinfo("Detection Complete", "No taxonomic inconsistencies found.")

    def load_corrections_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv;*.tsv")])
        if file_path:
            try:
                delimiter = self.ask_delimiter()
                corrections_df = pd.read_csv(file_path, sep=delimiter, dtype=str, low_memory=False)
                    
                if 'species' in corrections_df.columns and 'correction' in corrections_df.columns:
                    for index, row in corrections_df.iterrows():
                        species = row['species']
                        correction = row['correction']
                        if correction.lower() != 'no':
                            self.csv_data.loc[self.csv_data['species'] == species, 'species'] = correction
                    messagebox.showinfo("Corrections Applied", "The corrections have been applied successfully.")
                else:
                    messagebox.showerror("Error", "The CSV file must contain the columns 'species' and 'correction'.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not load the corrections CSV file: {e}")

    def show_occurrence_map(self):
        if self.csv_data is None:
            messagebox.showwarning("Warning", "Load a CSV file before showing the occurrence map.")
            return

        # Create window to select the percentage of data
        map_window = tk.Toplevel(self.root)
        map_window.title("Occurrence Map")

        tk.Label(map_window, text="Enter the percentage of data to display (0-100):").grid(row=0, column=0, padx=10, pady=5)
        percent_entry = tk.Entry(map_window)
        percent_entry.grid(row=0, column=1, padx=10, pady=5)
        percent_entry.insert(0, "10")

        def generate_map():
            try:
                percent = float(percent_entry.get()) / 100.0
                if percent <= 0 or percent > 1:
                    raise ValueError("The percentage must be between 0 and 100.")

                sample_data = self.csv_data.sample(frac=percent)

                # Check for numeric values in latitude and longitude columns
                sample_data['latitude'] = pd.to_numeric(sample_data['latitude'], errors='coerce')
                sample_data['longitude'] = pd.to_numeric(sample_data['longitude'], errors='coerce')
                sample_data = sample_data.dropna(subset=['latitude', 'longitude'])

                # Create a map
                map_center = [float(sample_data['latitude'].mean()), float(sample_data['longitude'].mean())]
                folium_map = folium.Map(location=map_center, zoom_start=4)

                for _, row in sample_data.iterrows():
                    folium.Marker([float(row['latitude']), float(row['longitude'])], popup=row['species']).add_to(folium_map)

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.html')
                folium_map.save(temp_file.name)

                webbrowser.open(temp_file.name)
                map_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Could not generate the map: {e}")

        tk.Button(map_window, text="Generate Map", command=generate_map).grid(row=1, column=0, columnspan=2, pady=10)

    def show_about(self):
        about_text = (
            "csv2xyd 2.1\n\n"
            "Author: Liria, Jonathan\n"
            " \n"
            "First version: Liria J, Szumik CA, Goloboff PA. (2021), Analysis of endemism of world arthropod distribution data supports biogeographic regions and many established subdivisions. Cladistics, 37: 559-570. https://doi.org/10.1111/cla.12448\n"
            " \n"
            "Cite as: Liria, J., Soto-Vivas, A. (2025). Csv2xyd: A Python Software for Processing Large Biodiversity Datasets for Endemism Analysis. Journal of Open Research Software, 13(1), p. 8. https://doi.org/10.5334/jors.538."
        )
        messagebox.showinfo("About", about_text)

    def process_csv(self):
        if self.csv_data is not None:
            try:
                selected_columns = [col for col, var in self.column_vars.items() if var.get()]
                if not selected_columns:
                    messagebox.showwarning("Warning", "You must select at least one column.")
                    return
                
                # Start timer
                start_time = time.time()

                # Preprocess data
                preprocessed_data = self.preprocess_data(self.csv_data)
                
                # Filter species with fewer occurrences than the specified minimum
                filtered_data = self.filter_species(preprocessed_data)
                
                self.generate_output_files(filtered_data, selected_columns)
                
                # Stop timer
                end_time = time.time()
                elapsed_time = end_time - start_time

                messagebox.showinfo("Success", f"The CSV file has been processed and the output files have been generated.\nElapsed time: {elapsed_time:.2f} seconds.")
                self.root.quit()  # Close the application after processing the file
            except Exception as e:
                messagebox.showerror("Error", f"Could not process the CSV file: {e}")
    
    def preprocess_data(self, data):
        # Remove duplicates based on 'species', 'longitude', 'latitude'
        preprocessed_data = data.drop_duplicates(subset=['species', 'longitude', 'latitude'])
        # Replace NaN values with a default value
        preprocessed_data.fillna("N/A", inplace=True)
        return preprocessed_data
    
    def filter_species(self, data):
        # Filter species with fewer occurrences than the specified minimum
        species_counts = data['species'].value_counts()
        species_to_keep = species_counts[species_counts >= self.min_occurrences.get()].index  # Changed to >=
        filtered_data = data[data['species'].isin(species_to_keep)]
        return filtered_data
    
    def generate_output_files(self, data, selected_columns):
        total_records = len(data)
        unique_species = data.drop_duplicates(subset=["genus", "species"])
        total_unique_species = len(unique_species)
        
        # Replace NaN values with a default value
        data.fillna("N/A", inplace=True)
        unique_species.fillna("N/A", inplace=True)
        
        # Generate output.tnt
        if self.current_csv_path:
            output_dir = os.path.dirname(self.current_csv_path)
        else:
            output_dir = os.getcwd()

        output_tnt_path = os.path.join(output_dir, "output.tnt")
        output_xyd_path = os.path.join(output_dir, "nufile.xyd")

        # Generate output.tnt
        with open(output_tnt_path, "w", encoding="utf-8") as f:
            f.write("taxonomy=; \ntaxname+300; \nmxram]; \nmxram 1200; \ntshrink!; \nxread \n'big big data' \n0 {}\n".format(total_unique_species))
            species_seen = set()
            for index, row in unique_species.iterrows():
                species_name_parts = [row['species'].replace(' ', '_'), '@']
                for col in ['phylum', 'class', 'order', 'family', 'genus']:
                    if col in selected_columns:
                        species_name_parts.append(row[col])
                species_name = '_'.join(species_name_parts)
                if species_name not in species_seen:
                    species_seen.add(species_name)
                    f.write(f"{species_name}\n")
            f.write(";\ntaxonomy];\nproc/;\n")
        
        # Generate nufile.xyd        
        with open(output_xyd_path, "w", encoding="utf-8") as f:
            f.write(f"nocommas \nspp {total_unique_species} \ngridx {self.grid_x.get()} 5 \ngridy {self.grid_y.get()} 5 \nfill {self.fill_value.get()} {self.fill_value.get()} \nassume {self.assume_value.get()} {self.assume_value.get()} \nlonglat \nautomatrix \nynegativemap \nxydata \n")
            species_seen = {}
            for index, row in data.iterrows():
                species_name = f"{row['species'].replace(' ', '_')}"
                if species_name not in species_seen:
                    species_seen[species_name] = []
                species_seen[species_name].append((float(row['longitude']), float(row['latitude'])))
            
            for idx, (species, coords) in enumerate(species_seen.items()):
                f.write(f"sp     {idx} [ {species} ]\n")
                for lon, lat in coords:
                    f.write(f"  {lon:.6f}  {lat:.6f} \n")
            messagebox.showinfo(
                "Output files generated",
                f"Files saved in:\n{output_dir}\n\n"
                f"output.tnt\n"
                f"nufile.xyd"
            )
    def process_large_csv_with_dask(self):
        files = filedialog.askopenfilenames(filetypes=[("CSV files", "*.csv;*.tsv")])
        if not files:
            messagebox.showwarning("Warning", "No files selected.")
            return

        try:
            delimiter = self.ask_delimiter()
            ddf = dd.read_csv(list(files), sep=delimiter, dtype=str, low_memory=False)
            columns = ddf.columns.tolist()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load CSV files: {e}")
            return

        # Create a new window to select columns and filters
        columns_window = tk.Toplevel(self.root)
        columns_window.title("Select Columns and Apply Filters")

        # Create a canvas with a scrollbar
        canvas = tk.Canvas(columns_window)
        scrollbar = tk.Scrollbar(columns_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        tk.Label(scrollable_frame, text="Select columns to include and apply filters:").pack(pady=5)
        column_vars = {col: tk.BooleanVar() for col in columns}
        filter_vars = {col: tk.StringVar() for col in columns}
        
        for col in columns:
            frame = tk.Frame(scrollable_frame)
            chk = tk.Checkbutton(frame, text=col, variable=column_vars[col])
            chk.pack(side=tk.LEFT)
            filter_entry = tk.Entry(frame, textvariable=filter_vars[col])
            filter_entry.pack(side=tk.RIGHT, padx=5)
            frame.pack(anchor='w', pady=2)
        
        def apply_filters():
            selected_columns = [col for col, var in column_vars.items() if var.get()]
            if not selected_columns:
                messagebox.showwarning("Warning", "You must select at least one column.")
                return

            try:
                filtered_ddf = ddf[selected_columns]
                
                # Apply filters based on user input
                for col in selected_columns:
                    filter_value = filter_vars[col].get()
                    if filter_value:
                        conditions = filter_value.split(',')
                        for condition in conditions:
                            condition = condition.strip()
                            if condition == 'isnumeric':
                                # Convert column to numeric and filter out non-numeric values
                                filtered_ddf[col] = dd.to_numeric(filtered_ddf[col], errors='coerce')
                                filtered_ddf = filtered_ddf.dropna(subset=[col])
                            elif condition == 'textonly':
                                # Filter cells that contain any text and exclude 'sp'
                                filtered_ddf = filtered_ddf[filtered_ddf[col].str.contains('.+', na=False) & ~filtered_ddf[col].str.contains('sp', na=False)]
                            else:
                                # Ensure the column is of type string before applying the filter
                                filtered_ddf[col] = filtered_ddf[col].astype(str)
                                if condition.startswith('!'):
                                    # Exclude condition
                                    condition = condition[1:]
                                    filtered_ddf = filtered_ddf[~filtered_ddf[col].str.contains(condition, na=False)]
                                else:
                                    # Include condition
                                    filtered_ddf = filtered_ddf[filtered_ddf[col].str.contains(condition, na=False)]

                # Rename decimalLatitude and decimalLongitude to latitude and longitude
                if 'decimalLatitude' in filtered_ddf.columns and 'decimalLongitude' in filtered_ddf.columns:
                    filtered_ddf = filtered_ddf.rename(columns={'decimalLatitude': 'latitude', 'decimalLongitude': 'longitude'})

                # Metadata for latitude and longitude
                filtered_ddf['latitude'] = filtered_ddf['latitude'].astype('float64')
                filtered_ddf['longitude'] = filtered_ddf['longitude'].astype('float64')

                filtered_ddf = filtered_ddf.compute()

                output_file = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
                if output_file:
                    filtered_ddf.to_csv(output_file, index=False)
                    messagebox.showinfo("Success", f"Filtered CSV has been saved to {output_file}")
                    columns_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Could not filter and save CSV files: {e}")

        tk.Button(scrollable_frame, text="Apply Filters", command=apply_filters).pack(pady=10)

    def merge_and_sort_csvs(self):
        files = filedialog.askopenfilenames(filetypes=[("CSV files", "*.csv;*.tsv")])
        if not files:
            messagebox.showwarning("Warning", "No files selected.")
            return

        missing_columns_files = []
        required_columns = ['genus', 'species', 'latitude', 'longitude']
        
        try:
            delimiter = self.ask_delimiter()
            # Load and check each CSV file
            for file in files:
                df = pd.read_csv(file, sep=delimiter, dtype=str, low_memory=False)
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    missing_columns_files.append((file, missing_columns))
            
            # If there are files with missing columns, alert the user
            if missing_columns_files:
                missing_info = "\n".join([f"{file}: Missing columns: {', '.join(missing)}" for file, missing in missing_columns_files])
                proceed = messagebox.askyesno("Missing Columns", f"The following files are missing required columns:\n\n{missing_info}\n\nDo you want to continue with the remaining files?")
                if not proceed:
                    return
            
            # Load and concatenate CSV files with necessary columns
            dfs = [pd.read_csv(file, sep=delimiter, dtype=str, low_memory=False) for file in files if file not in [f[0] for f in missing_columns_files]]
            combined_df = pd.concat(dfs, ignore_index=True)
            
            # Ensure the combined DataFrame contains at least the necessary columns
            combined_df = combined_df[required_columns + [col for col in combined_df.columns if col not in required_columns]]
            
            # Determine the sorting columns
            taxonomic_columns = ['phylum', 'class', 'order', 'family', 'genus', 'species']
            present_taxonomic_columns = [col for col in taxonomic_columns if col in combined_df.columns]
            
            # If only the necessary columns are present, sort by 'genus' and 'species'
            if present_taxonomic_columns == ['genus', 'species']:
                combined_df = combined_df.sort_values(by=['genus', 'species'])
            else:
                combined_df = combined_df.sort_values(by=present_taxonomic_columns)
            
            # Save the combined and sorted DataFrame to a new CSV file
            output_file = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if output_file:
                combined_df.to_csv(output_file, index=False)
                messagebox.showinfo("Success", f"Combined and sorted CSV has been saved to {output_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not merge and sort CSV files: {e}")

    def ask_delimiter(self):
        delimiter_window = tk.Toplevel(self.root)
        delimiter_window.title("Select Delimiter")

        tk.Label(delimiter_window, text="Select the delimiter used in the file:").pack(pady=5)

        delimiter = tk.StringVar(value=",")
        tk.Radiobutton(delimiter_window, text="Comma (,)", variable=delimiter, value=",").pack(anchor="w")
        tk.Radiobutton(delimiter_window, text="Tab (\t)", variable=delimiter, value="\t").pack(anchor="w")

        def set_delimiter():
            delimiter_window.destroy()

        tk.Button(delimiter_window, text="OK", command=set_delimiter).pack(pady=5)
        delimiter_window.wait_window()

        return delimiter.get()
    
    def reorder_columns(self):
        if self.csv_data is None:
            messagebox.showwarning("Warning", "Please open a CSV file first.")
            return

        # Create window with CSV lumns to select and reorder
        reorder_window = tk.Toplevel(self.root)
        reorder_window.title("Reorder Columns")

        tk.Label(reorder_window, text="Select and reorder columns:").pack(pady=5)

        # List columns
        column_listbox = tk.Listbox(reorder_window, selectmode=tk.SINGLE, exportselection=False)
        for col in self.csv_data.columns:
            column_listbox.insert(tk.END, col)
            column_listbox.pack(padx=10, pady=10)

        def move_up():
            selected_index = column_listbox.curselection()
            if not selected_index or selected_index[0] == 0:
                return
            index = selected_index[0]
            column_value = column_listbox.get(index)
            column_listbox.delete(index)
            column_listbox.insert(index - 1, column_value)
            column_listbox.select_set(index - 1)

        def move_down():
            selected_index = column_listbox.curselection()
            if not selected_index or selected_index[0] == column_listbox.size() - 1:
                return
            index = selected_index[0]
            column_value = column_listbox.get(index)
            column_listbox.delete(index)
            column_listbox.insert(index + 1, column_value)
            column_listbox.select_set(index + 1)

        def save_reordered_columns():
            reordered_columns = [column_listbox.get(i) for i in range(column_listbox.size())]
            # Dataframe update
            self.csv_data = self.csv_data[reordered_columns]

            # Save reorderd CSV file
            output_file = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if output_file:
                self.csv_data.to_csv(output_file, index=False)
                messagebox.showinfo("Success", f"Reordered CSV saved to {output_file}")
                reorder_window.destroy()

        up_button = tk.Button(reorder_window, text="Move Up", command=move_up)
        up_button.pack(pady=5)

        down_button = tk.Button(reorder_window, text="Move Down", command=move_down)
        down_button.pack(pady=5)

        save_button = tk.Button(reorder_window, text="Save Reordered Columns", command=save_reordered_columns)
        save_button.pack(pady=10)

    def run_geospatial_analysis(self):
        geospatial_window = tk.Toplevel(self.root)
        geospatial_window.title("Geospatial Analysis Tool")

        shapefile_path = tk.StringVar()
        csvfile_path = tk.StringVar()

        tk.Label(geospatial_window, text="Select the Shapefile:").grid(row=0, column=0, padx=10, pady=10)
        shapefile_entry = tk.Entry(geospatial_window, textvariable=shapefile_path, width=50)
        shapefile_entry.grid(row=0, column=1, padx=10, pady=10)
        shapefile_button = tk.Button(geospatial_window, text="Browse", command=lambda: self.browse_shapefile(shapefile_path))
        shapefile_button.grid(row=0, column=2, padx=10, pady=10)

        tk.Label(geospatial_window, text="Select the CSV file:").grid(row=1, column=0, padx=10, pady=10)
        tk.Entry(geospatial_window, textvariable=csvfile_path, width=50).grid(row=1, column=1, padx=10, pady=10)
        tk.Button(geospatial_window, text="Browse", command=lambda: self.browse_csvfile(csvfile_path)).grid(row=1, column=2, padx=10, pady=10)

        # Checkbuttons to select calculations
        species_richness_var = tk.BooleanVar()
        occurrence_abundance_var = tk.BooleanVar()
        hill_numbers_var = tk.BooleanVar()
        chao1_var = tk.BooleanVar()
        jack1_var = tk.BooleanVar()
        jack2_var = tk.BooleanVar()

        tk.Checkbutton(geospatial_window, text="Species Richness", variable=species_richness_var).grid(row=2, column=0, padx=10, pady=5)
        tk.Checkbutton(geospatial_window, text="Occurrence Abundance", variable=occurrence_abundance_var).grid(row=2, column=1, padx=10, pady=5)
        tk.Checkbutton(geospatial_window, text="Hill Numbers", variable=hill_numbers_var).grid(row=3, column=0, padx=10, pady=5)
        tk.Checkbutton(geospatial_window, text="Chao1 Index", variable=chao1_var).grid(row=3, column=1, padx=10, pady=5)
        tk.Checkbutton(geospatial_window, text="Jack1 Index", variable=jack1_var).grid(row=3, column=2, padx=10, pady=5)
        tk.Checkbutton(geospatial_window, text="Jack2 Index", variable=jack2_var).grid(row=3, column=3, padx=10, pady=5)

        # Grid parameters
        use_grid_var = tk.BooleanVar()
        tk.Checkbutton(geospatial_window, text="Use Grid", variable=use_grid_var, command=lambda: self.toggle_grid_params(use_grid_var, shapefile_entry, shapefile_button, cell_size_entry, x_min_entry, x_max_entry, y_min_entry, y_max_entry, suggest_limits_button, suggest_cell_button)).grid(row=4, column=0, padx=10, pady=5)
        tk.Label(geospatial_window, text="Cell Size (degrees):").grid(row=5, column=0, padx=10, pady=5)
        cell_size_entry = tk.Entry(geospatial_window, state='disabled')
        cell_size_entry.grid(row=5, column=1, padx=10, pady=5)

        tk.Label(geospatial_window, text="X Min (Longitude Min):").grid(row=6, column=0, padx=10, pady=5)
        x_min_entry = tk.Entry(geospatial_window, state='disabled')
        x_min_entry.grid(row=6, column=1, padx=10, pady=5)

        tk.Label(geospatial_window, text="Y Min (Latitude Min):").grid(row=7, column=0, padx=10, pady=5)
        y_min_entry = tk.Entry(geospatial_window, state='disabled')
        y_min_entry.grid(row=7, column=1, padx=10, pady=5)

        tk.Label(geospatial_window, text="X Max (Longitude Max):").grid(row=8, column=0, padx=10, pady=5)
        x_max_entry = tk.Entry(geospatial_window, state='disabled')
        x_max_entry.grid(row=8, column=1, padx=10, pady=5)

        tk.Label(geospatial_window, text="Y Max (Latitude Max):").grid(row=9, column=0, padx=10, pady=5)
        y_max_entry = tk.Entry(geospatial_window, state='disabled')
        y_max_entry.grid(row=9, column=1, padx=10, pady=5)

        suggest_limits_button = tk.Button(geospatial_window, text="Suggest Grid Limits", command=lambda: self.suggest_grid_limits(csvfile_path, x_min_entry, y_min_entry, x_max_entry, y_max_entry), state='disabled')
        suggest_limits_button.grid(row=4, column=1, padx=10, pady=5)

        suggest_cell_button = tk.Button(geospatial_window, text="Suggest Cell Size", command=lambda: self.suggest_cell_size(csvfile_path, cell_size_entry), state='disabled')
        suggest_cell_button.grid(row=5, column=2, padx=10, pady=5)

        # Buffer parameters
        buffer_size_var = tk.StringVar(value="Auto")
        tk.Label(geospatial_window, text="Buffer Size (Auto or Enter Value):").grid(row=10, column=0, padx=10, pady=5)
        tk.Entry(geospatial_window, textvariable=buffer_size_var).grid(row=10, column=1, padx=10, pady=5)

        tk.Button(geospatial_window, text="Run Analysis", command=lambda: self.run_analysis(shapefile_path, csvfile_path, species_richness_var, occurrence_abundance_var, hill_numbers_var, chao1_var, jack1_var, jack2_var, use_grid_var, cell_size_entry, x_min_entry, y_min_entry, x_max_entry, y_max_entry, buffer_size_var)).grid(row=11, columnspan=3, padx=10, pady=20)
    
    # Geospatial analysis functions
    def browse_shapefile(self, shapefile_path):
        filepath = filedialog.askopenfilename(filetypes=[("Shapefiles", "*.shp")])
        shapefile_path.set(filepath)

    def browse_csvfile(self, csvfile_path):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        csvfile_path.set(filepath)

    def suggest_grid_limits(self, csvfile_path, x_min_entry, y_min_entry, x_max_entry, y_max_entry):
        csvfile = csvfile_path.get()
        if not csvfile:
            messagebox.showwarning("Warning", "Please select the CSV file first.")
            return

        points = self.load_occurrences(csvfile)
        x_min, y_min, x_max, y_max = points.total_bounds

        x_min_entry.delete(0, tk.END)
        x_min_entry.insert(0, str(x_min))
        y_min_entry.delete(0, tk.END)
        y_min_entry.insert(0, str(y_min))
        x_max_entry.delete(0, tk.END)
        x_max_entry.insert(0, str(x_max))
        y_max_entry.delete(0, tk.END)
        y_max_entry.insert(0, str(y_max))

    def suggest_cell_size(self, csvfile_path, cell_size_entry):
        csvfile = csvfile_path.get()
        if not csvfile:
            messagebox.showwarning("Warning", "Please select the CSV file first.")
            return

        points = self.load_occurrences(csvfile)
        x_min, y_min, x_max, y_max = points.total_bounds
        area = (x_max - x_min) * (y_max - y_min)
        cell_size = np.sqrt(area / 1000)  # Example calculation, this can be adjusted

        cell_size_entry.delete(0, tk.END)
        cell_size_entry.insert(0, str(cell_size))

    def toggle_grid_params(self, use_grid_var, shapefile_entry, shapefile_button, cell_size_entry, x_min_entry, x_max_entry, y_min_entry, y_max_entry, suggest_limits_button, suggest_cell_button):
        if use_grid_var.get():
            shapefile_entry.config(state='disabled')
            shapefile_button.config(state='disabled')
            cell_size_entry.config(state='normal')
            x_min_entry.config(state='normal')
            y_min_entry.config(state='normal')
            x_max_entry.config(state='normal')
            y_max_entry.config(state='normal')
            suggest_limits_button.config(state='normal')
            suggest_cell_button.config(state='normal')
        else:
            shapefile_entry.config(state='normal')
            shapefile_button.config(state='normal')
            cell_size_entry.config(state='disabled')
            x_min_entry.config(state='disabled')
            x_max_entry.config(state='disabled')
            y_min_entry.config(state='disabled')
            y_max_entry.config(state='disabled')
            suggest_limits_button.config(state='disabled')
            suggest_cell_button.config(state='disabled')

    def run_analysis(self, shapefile_path, csvfile_path, species_richness_var, occurrence_abundance_var, hill_numbers_var, chao1_var, jack1_var, jack2_var, use_grid_var, cell_size_entry, x_min_entry, y_min_entry, x_max_entry, y_max_entry, buffer_size_var):
        shapefile = shapefile_path.get()
        csvfile = csvfile_path.get()
        buffer_size = buffer_size_var.get()
        
        if csvfile and (shapefile or use_grid_var.get()):
            calculations = {
                'species_richness': species_richness_var.get(),
                'occurrence_abundance': occurrence_abundance_var.get(),
                'hill_numbers': hill_numbers_var.get(),
                'chao1': chao1_var.get(),
                'jack1': jack1_var.get(),
                'jack2': jack2_var.get()
            }
            grid_params = None
            if use_grid_var.get():
                try:
                    cell_size = float(cell_size_entry.get())
                    x_min = float(x_min_entry.get())
                    y_min = float(y_min_entry.get())
                    x_max = float(x_max_entry.get())
                    y_max = float(y_max_entry.get())
                    grid_params = (x_min, y_min, x_max, y_max, cell_size)
                except ValueError:
                    messagebox.showwarning("Warning", "Please enter valid numeric values for the grid parameters.")
                    return
            self.main_geospatial_analysis(shapefile if not use_grid_var.get() else None, csvfile, calculations, grid_params, buffer_size)
        else:
            messagebox.showwarning("Warning", "Please select the CSV file and either a shapefile or use the grid option.")

    def load_shapefile(self, shapefile_path):
        """Load a shapefile using GeoPandas"""
        return gpd.read_file(shapefile_path)

    def load_occurrences(self, csv_file):
        """Load occurrences from a CSV file and convert them to a GeoDataFrame"""
        df = pd.read_csv(csv_file)
        df['geometry'] = df.apply(lambda row: Point(float(row['longitude']), float(row['latitude'])), axis=1)
        gdf = gpd.GeoDataFrame(df, geometry='geometry')
        gdf = gdf.set_crs("EPSG:4326")  # Set the CRS of points
        return gdf

    def create_grid(self, x_min, y_min, x_max, y_max, cell_size):
        """Create a grid of polygons (cells) covering the specified area"""
        if x_max <= x_min or y_max <= y_min:
            raise ValueError("X Max must be greater than X Min and Y Max must be greater than Y Min.")
        
        x_coords = np.arange(x_min, x_max, cell_size)
        y_coords = np.arange(y_min, y_max, cell_size)
        polygons = []
        for x in x_coords:
            for y in y_coords:
                polygons.append(Polygon([(x, y), (x + cell_size, y), (x + cell_size, y + cell_size), (x, y + cell_size)]))
        grid = gpd.GeoDataFrame({'geometry': polygons})
        grid = grid.set_crs("EPSG:4326")
        return grid

    def handle_points_on_edges(self, points, grid, buffer_size):
        """Handle points on the edges of grid cells by duplicating them in adjacent cells"""
        if buffer_size.lower() == "auto":
            buffer_size = 1e-9  # Small buffer to handle floating-point precision issues
        else:
            buffer_size = float(buffer_size)
            
        points_on_edges = points.copy()
        
        # Check if the points are on the vertical edges
        for x in grid.geometry.apply(lambda geom: geom.bounds[0]).unique():
            vertical_edge_points = points[points.geometry.apply(lambda point: abs(point.x - x) < buffer_size)]
            points_on_edges = pd.concat([points_on_edges, vertical_edge_points])

        # Check if the points are on the horizontal edges
        for y in grid.geometry.apply(lambda geom: geom.bounds[1]).unique():
            horizontal_edge_points = points[points.geometry.apply(lambda point: abs(point.y - y) < buffer_size)]
            points_on_edges = pd.concat([points_on_edges, horizontal_edge_points])
        
        return points_on_edges

    def calculate_hill_numbers(self, polygons, points, calculations, buffer_size):
        """Calculate Hill numbers (species richness, Shannon, Simpson), Jack1, Jack2, and Chao1 for each polygon"""
        points = points.to_crs(polygons.crs)  # Reproject points to match the CRS of the polygons

        # Ensure all geometries are valid
        points['geometry'] = points['geometry'].apply(lambda geom: geom if geom.is_valid else geom.buffer(0))
        polygons['geometry'] = polygons['geometry'].apply(lambda geom: geom if geom.is_valid else geom.buffer(0))

        # Handle points on edges
        points = self.handle_points_on_edges(points, polygons, buffer_size)

        # Remove existing index_right column if it exists
        if 'index_right' in points.columns:
            points = points.drop(columns=['index_right'])

        # Perform spatial join
        points_in_polygons = gpd.sjoin(points, polygons, how='left', predicate='within')
        
        results = {}
        
        if calculations['species_richness']:
            # Calculate species richness (number of unique species) in each polygon
            species_richness = points_in_polygons.groupby('index_right')['species'].nunique().reset_index()
            species_richness = species_richness.rename(columns={'index_right': 'polygon_index', 'species': 'species_richness'})
            results['species_richness'] = species_richness
        
        if calculations['occurrence_abundance']:
            # Calculate occurrence abundance for each species in each polygon and then sum them up
            species_abundance = points_in_polygons.groupby(['index_right', 'species']).size().reset_index(name='abundance')
            total_abundance = species_abundance.groupby('index_right')['abundance'].sum().reset_index(name='occurrence_abundance')
            total_abundance = total_abundance.rename(columns={'index_right': 'polygon_index'})
            results['occurrence_abundance'] = total_abundance
        
        if calculations['hill_numbers'] or calculations['chao1'] or calculations['jack1'] or calculations['jack2']:
            # Calculate Shannon, Simpson, Jack1, Jack2, and Chao1 indices for each polygon
            def hill_numbers(group):
                counts = group['species'].value_counts()
                proportions = counts / counts.sum()
                
                H0 = counts.count() if calculations['hill_numbers'] or calculations['chao1'] or calculations['jack1'] or calculations['jack2'] else np.nan  # Species richness
                H1 = np.exp(-np.sum(proportions * np.log(proportions))) if calculations['hill_numbers'] else np.nan  # Shannon diversity
                H2 = 1 / np.sum(proportions ** 2) if calculations['hill_numbers'] else np.nan  # Simpson diversity
                E1 = H1 / H0 if calculations['hill_numbers'] and H0 != 0 else np.nan  # Shannon evenness
                E2 = H2 / H0 if calculations['hill_numbers'] and H0 != 0 else np.nan  # Simpson evenness
                
                F1 = (counts == 1).sum()
                F2 = (counts == 2).sum()
                Chao1 = H0 + (F1 ** 2) / (2 * F2) if calculations['chao1'] and F2 > 0 else (H0 + F1 if calculations['chao1'] else np.nan)
                n = len(group)
                Jack1 = H0 + F1 * ((n - 1) / n) if calculations['jack1'] and n > 0 else (H0 if calculations['jack1'] else np.nan)
                Jack2 = H0 + (F1 * (2*n - 3) / n) - (F2 * (n - 2)**2 / (n * (n - 1))) if calculations['jack2'] and n > 1 else np.nan
                
                return pd.Series({'H0': H0, 'H1': H1, 'H2': H2, 'E1': E1, 'E2': E2, 'Chao1': Chao1, 'Jack1': Jack1, 'Jack2': Jack2})
            
            hill_df = points_in_polygons.groupby('index_right').apply(hill_numbers).reset_index()
            hill_df = hill_df.rename(columns={'index_right': 'polygon_index'})
            results['hill_numbers'] = hill_df
        
        return results

    def main_geospatial_analysis(self, shapefile_path, csv_file, calculations, grid_params=None, buffer_size="Auto"):
        try:
            if grid_params:
                x_min, y_min, x_max, y_max, cell_size = grid_params
                polygons = self.create_grid(x_min, y_min, x_max, y_max, cell_size)
            else:
                polygons = self.load_shapefile(shapefile_path)
            
            points = self.load_occurrences(csv_file)
            results = self.calculate_hill_numbers(polygons, points, calculations, buffer_size)
            
            # Combine counts with polygons
            polygons = polygons.reset_index().rename(columns={'index': 'polygon_index'})
            
            columns_to_keep = ['geometry']
            
            if 'species_richness' in results:
                polygons = polygons.merge(results['species_richness'], on='polygon_index', how='left')
                polygons['species_richness'] = polygons['species_richness'].fillna(0).astype(int)
                columns_to_keep.append('species_richness')
            
            if 'occurrence_abundance' in results:
                polygons = polygons.merge(results['occurrence_abundance'], on='polygon_index', how='left')
                polygons['occurrence_abundance'] = polygons['occurrence_abundance'].fillna(0).astype(int)
                columns_to_keep.append('occurrence_abundance')
            
            if 'hill_numbers' in results:
                polygons = polygons.merge(results['hill_numbers'], on='polygon_index', how='left')
                
                if calculations['hill_numbers']:
                    polygons['H0'] = polygons['H0'].fillna(0).astype(int)
                    polygons['H1'] = polygons['H1'].fillna(0)
                    polygons['H2'] = polygons['H2'].fillna(0)
                    polygons['E1'] = polygons['E1'].fillna(0)
                    polygons['E2'] = polygons['E2'].fillna(0)
                    columns_to_keep.extend(['H0', 'H1', 'H2', 'E1', 'E2'])
                
                if calculations['chao1']:
                    polygons['Chao1'] = polygons['Chao1'].fillna(0)
                    columns_to_keep.append('Chao1')
                
                if calculations['jack1']:
                    polygons['Jack1'] = polygons['Jack1'].fillna(0)
                    columns_to_keep.append('Jack1')
                
                if calculations['jack2']:
                    polygons['Jack2'] = polygons['Jack2'].fillna(0)
                    columns_to_keep.append('Jack2')
            
            polygons = polygons[columns_to_keep]
            
            # Display results
            print(polygons.head())
            
            # Save result to a new shapefile if needed
            polygons.to_file("polygons_with_calculations.shp")
            
            messagebox.showinfo("Completed", "Processing completed. Results saved to 'polygons_with_calculations.shp'.")
        except ValueError as e:
            messagebox.showwarning("Warning", str(e))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def launch_ndm_out_analyzer(self):
        try:
            from NDMoutAnalyzer import NDMOutAnalyzer
            ndm_window = tk.Toplevel(self.root)
            NDMOutAnalyzer(ndm_window)
        except Exception as e:
            messagebox.showerror(
                "NDM/vNDM Analyzer Error",
                f"Could not launch NDM/vNDM Output Analyzer:\n{e}"
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = CSVProcessorApp(root)
    root.mainloop()
