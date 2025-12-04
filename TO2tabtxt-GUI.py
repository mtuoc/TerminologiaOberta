import xml.etree.ElementTree as ET
import csv
import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, font
import sys

# --- Core Functions (From TO2tabtxt.py) ---

def clean_and_split_term(term):
    """
    Cleans a term by removing content within square brackets [] and parentheses (),
    and then splits the resulting string by the pipe character (|).

    Args:
        term (str): The raw term string from the XML.

    Returns:
        list[str]: A list of cleaned, individual terms.
    """
    # 1. Remove content within parentheses () and square brackets []
    cleaned_term = re.sub(r'\s*\(.*?\)|\s*\[.*?\]', '', term).strip()

    # 2. Split the term by the pipe character (|)
    if '|' in cleaned_term:
        # Split and filter out any empty strings that might result from trailing/leading pipes
        split_terms = [t.strip() for t in cleaned_term.split('|') if t.strip()]
    else:
        # If no pipe, return the single cleaned term in a list, ensuring it's not empty
        split_terms = [cleaned_term] if cleaned_term else []
        
    return split_terms

def normalize_filter_list(filter_str):
    """
    Normalizes a filter string (separated by comma, space, or newline).
    Returns a set of lowercase, stripped values, or None if the input is empty.
    """
    if not filter_str:
        return None
    
    # Use regex to split the string by commas, spaces, or newlines, and filter empty strings
    filter_list = re.split(r'[,\s\n]+', filter_str)
    
    # Normalize: strip whitespace, lowercase, and convert to a set for fast lookup
    normalized_set = {f.strip().lower() for f in filter_list if f.strip()}
    
    return normalized_set if normalized_set else None

def passes_filters(category, denomination_type, denomination_jerarquia, normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
    """
    Checks if a denomination passes all applied filters.
    Returns True if the denomination is accepted, False otherwise.
    """
    # 1. Category Prefix Filter
    if normalized_category_prefixes:
        category = category.strip().lower()
        if not category:
            return False 

        category_match = False
        for prefix in normalized_category_prefixes:
            if category.startswith(prefix):
                category_match = True
                break
        
        if not category_match:
            return False
            
    # 2. Type Filter (tipus)
    if normalized_type_filters:
        denomination_type = denomination_type.strip().lower()
        if denomination_type not in normalized_type_filters:
            return False

    # 3. Hierarchy Filter (jerarquia)
    if normalized_jerarquia_filter:
        denomination_jerarquia = denomination_jerarquia.strip().lower()
        if denomination_jerarquia not in normalized_jerarquia_filter:
            return False
            
    return True

def xml_to_tsv(input_file, output_file, sl, tl, include_area, include_definition, include_category, include_type, include_hierarchy, category_starts, type_filter, hierarchy_filter, log_func):
    """
    Converts an XML glossary file to a Tab-Separated Values (TSV) file,
    with optional filtering and inclusion of various data fields.
    """
    log_func("Starting XML to TSV conversion...", 'info')

    if not input_file or not output_file or not sl or not tl:
        log_func("Error: Please provide all required files and language codes.", 'error')
        return

    try:
        # Load and parse the XML file
        tree = ET.parse(input_file)
        root = tree.getroot()
        log_func(f"XML file loaded: {input_file}", 'info')

    except FileNotFoundError:
        log_func(f"Error: Input file '{input_file}' not found.", 'error')
        return
    except ET.ParseError:
        log_func(f"Error: Input file '{input_file}' is not a valid XML.", 'error')
        return
    except Exception as e:
        log_func(f"An unexpected error occurred during XML parsing: {e}", 'error')
        return
    
    # --- Normalization of Filters ---
    normalized_category_prefixes = normalize_filter_list(category_starts)
    normalized_type_filters = normalize_filter_list(type_filter)
    normalized_jerarquia_filter = normalize_filter_list(hierarchy_filter)
    
    # --- TSV Header Definition ---
    header = ['ID', 'SL_Term', 'TL_Term', 'SL', 'TL']
    if include_area: header.append('Thematic_Area')
    if include_definition: header.append('SL_Definition')
    if include_category: header.append('Term_Category')
    if include_type: header.append('Term_Type')
    if include_hierarchy: header.append('Term_Hierarchy')

    entry_count = 0
    exported_rows = 0
    
    # --- Opening and Writing the TSV File ---
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as tsvfile:
            # Use '\t' as the delimiter for TSV
            writer = csv.writer(tsvfile, delimiter='\t')
            #writer.writerow(header) # Write header
            
            # Iterate over each <fitxa> (glossary entry)
            for entry in root.findall('.//fitxa'):
                entry_count += 1
                entry_id = entry.get('num', f'e{entry_count}')
                
                # Extract entry-level fields
                # Replace newlines with spaces for clean TSV export
                area_tematica = entry.findtext('areatematica', default='').strip().replace('\n', ' ')
                
                definitions_sl = ''
                if include_definition:
                    # Find the definition in the Source Language (SL)
                    for definition in entry.findall('definicio'):
                        language = definition.get('llengua')
                        if language == sl:
                            definitions_sl = definition.findtext('.', default='').strip().replace('\n', ' ')
                            break
                
                filtered_denominations = []
                
                # Extraction and filtering of denominations
                for denomination in entry.findall('denominacio'):
                    language = denomination.get('llengua', '').strip().lower()
                    raw_term = denomination.findtext('.', default='').strip()
                    category = denomination.get('categoria', '').strip() 
                    denomination_type = denomination.get('tipus', '').strip()
                    denomination_jerarquia = denomination.get('jerarquia', '').strip()
                    
                    if not raw_term or (language != sl and language != tl):
                        continue
                    
                    # Check all filters
                    if not passes_filters(category, denomination_type, denomination_jerarquia, normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
                        continue
                    
                    # Clean and split terms (handles brackets/parentheses and '|')
                    processed_terms = clean_and_split_term(raw_term)
                    
                    if not processed_terms:
                        continue
                        
                    # Store data for each split term
                    for term in processed_terms:
                        filtered_denominations.append({
                            'lang': language,
                            'term': term,
                            'category': category,
                            'type': denomination_type,
                            'hierarchy': denomination_jerarquia
                        })

                # --- TSV Row Generation ---
                
                terms_sl = [d for d in filtered_denominations if d['lang'] == sl]
                terms_tl = [d for d in filtered_denominations if d['lang'] == tl]

                # Skip entry if no SL terms pass filters
                if not terms_sl:
                    continue
                
                # Create a list of SL-TL combinations
                if terms_tl:
                    # Cross-product of all SL and TL combinations
                    combinations = [(tsl, ttl) for tsl in terms_sl for ttl in terms_tl]
                else:
                    # Only SL terms (for monolingual SL entries that pass filters)
                    empty_tl_data = {'term': '', 'category': '', 'type': '', 'hierarchy': ''}
                    combinations = [(tsl, empty_tl_data) for tsl in terms_sl]
                    
                # Write each combination as a TSV row
                for tsl_data, ttl_data in combinations:
                    #row = [entry_id, tsl_data['term'], ttl_data.get('term', ''), sl, tl]
                    row = [tsl_data['term'], ttl_data.get('term', '')]
                    # Optional fields
                    if include_area: row.append(area_tematica)
                    if include_definition: row.append(definitions_sl)
                    
                    # Category/Type/Hierarchy (extracted from the primary SL denomination)
                    if include_category: row.append(tsl_data.get('category', ''))
                    if include_type: row.append(tsl_data.get('type', ''))
                    if include_hierarchy: row.append(tsl_data.get('hierarchy', ''))
                    
                    writer.writerow(row)
                    exported_rows += 1

    except IOError:
        log_func(f"Error: Could not write to the output file '{output_file}'. Check permissions.", 'error')
        return
    except Exception as e:
        log_func(f"An unexpected error occurred: {e}", 'error')
        return

    # --- Summary Message ---
    
    log_func("-" * 50, 'success')
    log_func(f"XML entries processed: {entry_count}. TSV rows generated: {exported_rows}.", 'info')
    
    if exported_rows == 0:
        log_func("Warning: No TSV rows generated. Check your filters and language codes.", 'info')

    log_func("Conversion to Tab-Separated File (.txt) completed successfully.", 'success')
    log_func(f"File saved to: **{output_file}**", 'success')
    log_func("-" * 50, 'success')


# --- TKINTER GUI APPLICATION ---

class XML2TSV_App:
    def __init__(self, master):
        self.master = master
        master.title("TO2tabtxt Converter")

        # 1. Crear el Canvas i el Scrollbar (Contenidors d'scroll)
        self.main_canvas = tk.Canvas(master)
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(master, orient=tk.VERTICAL, command=self.main_canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 2. Configurar el Canvas
        self.main_canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 3. Crear el Frame que contindrà TOTS els widgets de l'aplicació
        self.content_frame = tk.Frame(self.main_canvas, padx=20, pady=20)
        # El Frame es crea com a finestra dins del Canvas
        self.frame_window = self.main_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        
        # Bindejar esdeveniments per assegurar el comportament del scroll:
        # A. Quan el Frame interior canvia de mida (pel contingut): recalcular la regió de scroll
        self.content_frame.bind('<Configure>', self._on_frame_configure)
        # B. Quan la finestra principal canvia de mida (per l'usuari): assegurar que el Frame interior ompli l'amplada
        self.main_canvas.bind('<Configure>', self._on_canvas_configure)
        # C. Suport a la roda del ratolí
        self.main_canvas.bind_all('<MouseWheel>', self._on_mousewheel) # Windows/Linux
        self.main_canvas.bind_all('<Button-4>', self._on_mousewheel) # Linux/Macos scroll up
        self.main_canvas.bind_all('<Button-5>', self._on_mousewheel) # Linux/Macos scroll down

        # Custom font for the main button
        self.bold_font = font.Font(family="Helvetica", size=12, weight="bold")

        # Variables for user input (Declarades al master per consistència)
        self.input_file = tk.StringVar(master, value="")
        self.output_file = tk.StringVar(master, value="") 
        self.sl_code = tk.StringVar(master, value="")
        self.tl_code = tk.StringVar(master, value="")
        
        # Inclusion Checkboxes (BooleanVar: Default False)
        self.include_area = tk.BooleanVar(master, value=False) 
        self.include_definition = tk.BooleanVar(master, value=False) 
        self.include_category = tk.BooleanVar(master, value=False) 
        self.include_type = tk.BooleanVar(master, value=False) 
        self.include_hierarchy = tk.BooleanVar(master, value=False) 

        # Filter Text Inputs (StringVar: Default empty)
        self.category_starts = tk.StringVar(master, value="")
        self.type_filter = tk.StringVar(master, value="")
        self.hierarchy_filter = tk.StringVar(master, value="")

        # Passar el content_frame a la funció per crear els widgets allà dins
        self.create_widgets(self.content_frame)
    
    def _on_frame_configure(self, event):
        """Ajusta l'scrollregion del canvas quan el frame interior canvia de mida."""
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        
    def _on_canvas_configure(self, event):
        """Ajusta l'amplada de la finestra del frame al canvas."""
        # Aquesta línia fa que el Frame interior s'expandeixi per omplir l'amplada del Canvas.
        self.main_canvas.itemconfig(self.frame_window, width=event.width)
        
    def _on_mousewheel(self, event):
        """Permet fer scroll amb la roda del ratolí (multiplataforma)."""
        if event.num == 4: # Linux/Mac scroll up
            delta = -1
        elif event.num == 5: # Linux/Mac scroll down
            delta = 1
        elif hasattr(event, 'delta') and event.delta != 0: # Windows
            delta = int(-1 * (event.delta / 120))
        else:
            return

        self.main_canvas.yview_scroll(delta, "units")

    def create_widgets(self, master):
        # ------------------- Input/Output Frame -------------------
        io_frame = tk.LabelFrame(master, text="File and Language Configuration", padx=15, pady=10, font=self.bold_font)
        io_frame.pack(fill='x', pady=10)

        # Input File
        tk.Label(io_frame, text="Input XML File:", anchor='w').grid(row=0, column=0, sticky='w', pady=5)
        tk.Entry(io_frame, textvariable=self.input_file, width=60).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(io_frame, text="Browse...", command=self.browse_input, bg='#e0e0e0').grid(row=0, column=2, padx=5, pady=5)

        # Output File
        tk.Label(io_frame, text="Output File (.txt - TSV):", anchor='w').grid(row=1, column=0, sticky='w', pady=5)
        tk.Entry(io_frame, textvariable=self.output_file, width=60).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(io_frame, text="Save As...", command=self.browse_output, bg='#e0e0e0').grid(row=1, column=2, padx=5, pady=5)

        # Language Codes
        lang_frame = tk.Frame(io_frame)
        lang_frame.grid(row=2, column=0, columnspan=3, sticky='w', pady=10)
        
        tk.Label(lang_frame, text="Source Language (SL, e.g., 'en'):").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(lang_frame, textvariable=self.sl_code, width=5).pack(side=tk.LEFT, padx=(0, 30))
        
        tk.Label(lang_frame, text="Target Language (TL, e.g., 'fr'):").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(lang_frame, textvariable=self.tl_code, width=5).pack(side=tk.LEFT)

        # ------------------- Include Fields Frame -------------------
        include_frame = tk.LabelFrame(master, text="Optional Output Columns", padx=15, pady=10, font=self.bold_font)
        include_frame.pack(fill='x', pady=10)
        
        # Row 1 of inclusions
        row1 = tk.Frame(include_frame)
        row1.pack(fill='x', pady=5)
        tk.Checkbutton(row1, text="Thematic Area", variable=self.include_area).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(row1, text="Definition (from SL)", variable=self.include_definition).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(row1, text="Category (Part of Speech)", variable=self.include_category).pack(side=tk.LEFT, padx=10)

        # Row 2 of inclusions (Denomination fields)
        row2 = tk.Frame(include_frame)
        row2.pack(fill='x', pady=5)
        tk.Checkbutton(row2, text="Type (tipus)", variable=self.include_type).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(row2, text="Hierarchy (jerarquia)", variable=self.include_hierarchy).pack(side=tk.LEFT, padx=10)


        # ------------------- Filter Frame -------------------
        filter_frame = tk.LabelFrame(master, text="Denomination Filters (SL only)", padx=15, pady=10, font=self.bold_font)
        filter_frame.pack(fill='x', pady=10)

        # Category Filter
        tk.Label(filter_frame, text="Category Prefixes (e.g., 'n', 'v'):").grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.category_starts, width=60).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # Type Filter
        tk.Label(filter_frame, text="Term Types (e.g., 'principal', 'preferred'):").grid(row=1, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.type_filter, width=60).grid(row=1, column=1, padx=5, pady=2, sticky='ew')
        
        # Hierarchy Filter
        tk.Label(filter_frame, text="Term Hierarchies (e.g., 'pral.', 'acronym'):").grid(row=2, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.hierarchy_filter, width=60).grid(row=2, column=1, padx=5, pady=2, sticky='ew')
        
        tk.Label(filter_frame, text="Separators for filters: comma, space, or newline.", font=('Helvetica', 9, 'italic')).grid(row=3, column=0, columnspan=2, sticky='w', pady=5)
        
        # ------------------- Process Button and Log -------------------
        
        tk.Button(master, 
                  text="RUN CONVERSION", 
                  command=self.run_conversion, 
                  font=self.bold_font,
                  bg='#4CAF50', fg='white',
                  activebackground='#66BB6A', activeforeground='white',
                  relief=tk.RAISED,
                  padx=10, pady=5).pack(fill='x', pady=15)

        tk.Label(master, text="Operation Log:", anchor='w').pack(fill='x')
        self.log_text = scrolledtext.ScrolledText(master, height=10, state='disabled', wrap=tk.WORD, font=('Courier New', 10), bg='#f0f0f0')
        self.log_text.pack(fill='both', expand=True)

    def browse_input(self):
        filename = filedialog.askopenfilename(
            defaultextension=".xml",
            filetypes=[("XML Glossary Files", "*.xml"), ("All files", "*.*")]
        )
        if filename:
            self.input_file.set(filename)

    def browse_output(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Tab Separated File", "*.txt"),
                ("All files", "*.*")
            ],
            initialfile=self.output_file.get() if self.output_file.get() else "output.txt"
        )
        if filename:
            self.output_file.set(filename)

    def log(self, message, message_type='info'):
        """Writes a message to the log area with color coding."""
        self.log_text.config(state='normal')
        
        tag_map = {'info': 'blue', 'error': 'red', 'success': 'green'}
        
        # Configure tags once
        if not hasattr(self.log_text, 'tag_configured_flag'):
            for msg_type, color in tag_map.items():
                self.log_text.tag_config(msg_type, foreground=color)
            self.log_text.tag_config('bold', font=('Courier New', 10, 'bold'))
            setattr(self.log_text, 'tag_configured_flag', True)

        tags_to_apply = (message_type, 'bold') if message_type == 'success' else (message_type,)

        # Remove markdown bolding for the log display
        clean_message = message.replace('**', '') 
        self.log_text.insert(tk.END, clean_message + '\n', tags_to_apply)
        self.log_text.yview(tk.END)
        self.log_text.config(state='disabled')
        
        self.master.update_idletasks() # Ensure immediate display

    def run_conversion(self):
        """Executes the conversion with user data."""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # Basic validation
        if not self.input_file.get() or not self.output_file.get() or not self.sl_code.get() or not self.tl_code.get():
            self.log("ERROR: All File and Language Code fields are mandatory.", 'error')
            return

        try:
            # Call the main conversion function with values from the GUI variables
            xml_to_tsv(
                input_file=self.input_file.get(),
                output_file=self.output_file.get(),
                sl=self.sl_code.get().strip().lower(),
                tl=self.tl_code.get().strip().lower(),
                include_area=self.include_area.get(),
                include_definition=self.include_definition.get(),
                # All other includes (mandatory from original script arguments)
                include_category=self.include_category.get(),
                include_type=self.include_type.get(),
                include_hierarchy=self.include_hierarchy.get(),
                # Filters
                category_starts=self.category_starts.get(),
                type_filter=self.type_filter.get(),
                hierarchy_filter=self.hierarchy_filter.get(),
                log_func=self.log
            )
        except Exception as e:
            self.log(f"A critical error interrupted the process: {e}", 'error')

if __name__ == '__main__':
    try:
        root = tk.Tk()
        # Establir una mida inicial raonable i permetre la redimensió
        root.geometry("800x700") 
        app = XML2TSV_App(root)
        root.mainloop()
    except Exception as e:
        # En cas que Tkinter falli en la inicialització
        print(f"Error initializing the GUI: {e}")