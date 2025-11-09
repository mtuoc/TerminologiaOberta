import tkinter as tk
from tkinter import filedialog, scrolledtext, font
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import sys

# ==============================================================================
# 1. CORE CONVERSION LOGIC (Support Functions)
# ==============================================================================

# Register the 'xml' namespace for 'xml:lang'
ET.register_namespace('xml', "http://www.w3.org/XML/1998/namespace")

def indent(elem, level=0, space="  "):
    """Formats the XML tree for readability (pretty print)."""
    i = "\n" + level * space
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + space
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level + 1, space)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if not elem.tail or not elem.tail.strip():
            elem.tail = i

def clean_and_split_term(term):
    """Cleans a term by removing content within parentheses/brackets and splits it by '|'."""
    # Clean: remove content within ( ) or [ ]
    cleaned_term = re.sub(r'\s*\(.*?\)|\s*\[.*?\]', '', term).strip()
    
    # Split: split by '|'
    if '|' in cleaned_term:
        split_terms = [t.strip() for t in cleaned_term.split('|') if t.strip()]
    else:
        split_terms = [cleaned_term] if cleaned_term else []
    return split_terms

def normalize_filter_list(filter_str):
    """Normalizes a filter string (comma, space, or newline separated) into a set."""
    if not filter_str:
        return None
    # Split by any combination of comma, space, or newline
    filter_list = re.split(r'[,\s\n]+', filter_str)
    # Convert to lowercase and strip whitespace, ensuring no empty strings remain
    normalized_set = {f.strip().lower() for f in filter_list if f.strip()}
    return normalized_set if normalized_set else None

def passes_filters(category, denomination_type, denomination_jerarquia, normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
    """Checks if a denomination passes all applied filters (Category, Type, Hierarchy)."""
    
    # 1. Category Prefix Filter
    if normalized_category_prefixes:
        category = category.strip().lower()
        if not category or not any(category.startswith(prefix) for prefix in normalized_category_prefixes):
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

def xml_to_tbx(input_file, output_file, sl, tl, 
               include_area, include_definition, include_category, category_starts, 
               include_type, type_filter, include_hierarchy, hierarchy_filter, log_func):
    """
    Main function to convert the XML glossary to TBX format.
    """
    log_func("Starting XML to TBX conversion...", 'info')

    # --- 1. TBX Structure Setup ---
    NS_TBX = "urn:iso:std:iso:61440:TBX-core" 
    NS_XML = "http://www.w3.org/XML/1998/namespace"
    
    martif = ET.Element('martif', attrib={'type': 'TBX', 'version': '2.0', 'xmlns': NS_TBX, 'xmlns:xml': NS_XML})
    
    # martifHeader
    martifHeader = ET.SubElement(martif, 'martifHeader')
    fileDesc = ET.SubElement(martifHeader, 'fileDesc')
    ET.SubElement(fileDesc, 'titleStmt').text = f"TBX Conversion from {input_file}"
    ET.SubElement(fileDesc, 'pubStmt')
    encodingDesc = ET.SubElement(martifHeader, 'encodingDesc')
    ET.SubElement(encodingDesc, 'encoding', attrib={'ref': 'UTF-8', 'name': 'UNICODE'})
    creationDate = ET.SubElement(martifHeader, 'creationDate')
    creationDate.set('date', datetime.now().strftime("%Y-%m-%d"))

    # text body
    text = ET.SubElement(martif, 'text')
    body = ET.SubElement(text, 'body')

    # --- 2. Load and Parse XML ---
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()
        log_func(f"XML file loaded successfully: {input_file}", 'info')
    except FileNotFoundError:
        log_func(f"Error: Input file not found: {input_file}", 'error')
        return
    except Exception as e:
        log_func(f"Error during XML parsing: {e}", 'error')
        return

    # --- 3. Normalize Filters ---
    normalized_category_prefixes = normalize_filter_list(category_starts)
    normalized_type_filters = normalize_filter_list(type_filter)
    normalized_jerarquia_filter = normalize_filter_list(hierarchy_filter)
    
    entry_count = 0
    exported_entries = 0
    
    # --- 4. Iterate and Convert ---
    
    # Find all <fitxa> elements throughout the tree
    for entry in root.findall('.//fitxa'):
        entry_count += 1
        entry_id = entry.get('num', f'e{entry_count}')
        
        # 4.1 Extract entry-level fields
        area_tematica = entry.findtext('areatematica', default='').strip()
        
        definitions = {}
        # Collect definitions only for SL and TL
        for definition in entry.findall('definicio'):
            language = definition.get('llengua', '').strip().lower()
            text_content = definition.findtext('.', default='').strip()
            if text_content and language in [sl, tl]:
                definitions[language] = text_content
        
        # 4.2 Group all denominations by language
        denominations_by_lang = {sl: [], tl: []}
        has_valid_term = False
        
        for denomination in entry.findall('denominacio'):
            language = denomination.get('llengua', '').strip().lower()
            raw_term = denomination.findtext('.', default='').strip()
            
            # Extract denomination fields
            category = denomination.get('categoria', '').strip() 
            denomination_type = denomination.get('tipus', '').strip()
            denomination_jerarquia = denomination.get('jerarquia', '').strip()
            
            if language not in [sl, tl] or not raw_term:
                continue
            
            # Apply all filters. If the SL denomination fails the filter, we skip the whole <fitxa>.
            if language == sl:
                if not passes_filters(category, denomination_type, denomination_jerarquia, 
                                      normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
                    continue # Skip this SL denomination if it fails filters
                else:
                    has_valid_term = True # Found at least one valid SL denomination that passes filters

            # Clean and split terms 
            processed_terms = clean_and_split_term(raw_term)
            
            for term in processed_terms:
                denominations_by_lang[language].append({
                    'term': term,
                    'category': category,
                    'type': denomination_type,
                    'hierarchy': denomination_jerarquia
                })
        
        # Filter: ensure at least one valid SL denomination was processed
        if not has_valid_term or not denominations_by_lang.get(sl):
            continue

        # 4.3 Generate TBX <termEntry> if valid terms were found
        if has_valid_term:
            termEntry = ET.SubElement(body, 'termEntry', attrib={'id': entry_id})
            exported_entries += 1
            
            # Add descriptive fields at the entry level
            if include_area and area_tematica:
                descrip = ET.SubElement(termEntry, 'descrip', attrib={'type': 'subject'})
                descrip.text = area_tematica
            
            # Process each language
            for lang_code in [sl, tl]:
                # Export if it has terms OR if it has a definition
                if denominations_by_lang.get(lang_code) or (include_definition and lang_code in definitions):
                    langSet = ET.SubElement(termEntry, 'langSet', attrib={'xml:lang': lang_code})

                    # Add definition 
                    if include_definition and lang_code in definitions and definitions[lang_code]:
                        descrip_def = ET.SubElement(langSet, 'descrip', attrib={'type': 'definition'})
                        descrip_def.text = definitions[lang_code]
                    
                    # Add all terms for this language
                    for d in denominations_by_lang.get(lang_code, []):
                        tig = ET.SubElement(langSet, 'tig')
                        
                        term = ET.SubElement(tig, 'term')
                        term.text = d['term']
                        
                        # Category (Part of Speech)
                        if include_category and d['category']:
                            termNote_cat = ET.SubElement(tig, 'termNote', attrib={'type': 'partOfSpeech'})
                            termNote_cat.text = d['category']

                        # Type (Term Type)
                        if include_type and d['type']:
                            termNote_type = ET.SubElement(tig, 'termNote', attrib={'type': 'termType'})
                            termNote_type.text = d['type']

                        # Hierarchy (Normative Authorization)
                        if include_hierarchy and d['hierarchy']:
                            termNote_hier = ET.SubElement(tig, 'termNote', attrib={'type': 'normativeAuthorization'})
                            termNote_hier.text = d['hierarchy']


    # --- 5. Finalize and Save TBX ---
    indent(martif)

    try:
        tree = ET.ElementTree(martif)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)

    except IOError:
        log_func(f"Error: Could not write to the output file '{output_file}'. Check permissions.", 'error')
        return
    except Exception as e:
        log_func(f"An unexpected error occurred during writing: {e}", 'error')
        return

    # --- 6. Summary Message ---
    log_func("-" * 50, 'success')
    log_func(f"XML entries processed: {entry_count}. TBX entries generated: {exported_entries}.", 'info')
    
    if exported_entries == 0:
        log_func("Warning: No TBX entries were generated. Please check your filters and language codes.", 'info')

    log_func("✅ TBX conversion completed successfully.", 'success')
    log_func(f"File saved to: **{output_file}**", 'success')
    log_func("-" * 50, 'success')


# ==============================================================================
# 2. TKINTER GUI LOGIC (Interface Logic)
# ==============================================================================

class XML2TBX_App:
    def __init__(self, master):
        self.master = master
        master.title("XML Glossary to TBX Converter")
        master.configure(padx=20, pady=20)

        self.bold_font = font.Font(family="Helvetica", size=12, weight="bold")

        # Variables for user input (Defaulted to empty/False)
        self.input_file = tk.StringVar(master, value="")
        # IMPORTANT: output_file defaults to empty
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

        self.create_widgets(master)
    
    def create_widgets(self, master):
        # ------------------- Input/Output Frame -------------------
        io_frame = tk.LabelFrame(master, text="File and Language Configuration", padx=15, pady=10, font=self.bold_font)
        io_frame.pack(fill='x', pady=10)
        
        # Configure column weights for the button/entry layout
        io_frame.columnconfigure(0, weight=1) # Button column
        io_frame.columnconfigure(1, weight=3) # Entry column

        # 1. Input File (Button + Entry)
        tk.Button(io_frame, 
                  text="Select Input XML Glossary File...", 
                  command=self.browse_input, 
                  bg='#e0e0e0', 
                  anchor='w').grid(row=0, column=0, padx=5, pady=5, sticky='ew')
        tk.Entry(io_frame, textvariable=self.input_file, width=60).grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        # 2. Output File (Button + Entry)
        tk.Button(io_frame, 
                  text="Save Output TBX Termbase As (.tbx)...", 
                  command=self.browse_output, 
                  bg='#e0e0e0', 
                  anchor='w').grid(row=1, column=0, padx=5, pady=5, sticky='ew')
        tk.Entry(io_frame, textvariable=self.output_file, width=60).grid(row=1, column=1, padx=5, pady=5, sticky='ew')


        # 3. Language Codes
        lang_frame = tk.Frame(io_frame)
        lang_frame.grid(row=2, column=0, columnspan=2, sticky='w', pady=10)
        
        tk.Label(lang_frame, text="Source Language Code (SL, e.g., 'en'):").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(lang_frame, textvariable=self.sl_code, width=5).pack(side=tk.LEFT, padx=(0, 30))
        
        tk.Label(lang_frame, text="Target Language Code (TL, e.g., 'es'):").pack(side=tk.LEFT, padx=(0, 5))
        tk.Entry(lang_frame, textvariable=self.tl_code, width=5).pack(side=tk.LEFT)

        # ------------------- Inclusion Fields Frame -------------------
        include_frame = tk.LabelFrame(master, text="Optional Output Elements (TBX)", padx=15, pady=10, font=self.bold_font)
        include_frame.pack(fill='x', pady=10)
        
        # Row 1 of inclusions
        row1 = tk.Frame(include_frame)
        row1.pack(fill='x', pady=5)
        tk.Checkbutton(row1, text="Thematic Area (TBX: subject)", variable=self.include_area).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(row1, text="Definition (TBX: definition)", variable=self.include_definition).pack(side=tk.LEFT, padx=10)
        
        # Row 2 of inclusions (Term Notes)
        row2 = tk.Frame(include_frame)
        row2.pack(fill='x', pady=5)
        # Category (categoria) -> partOfSpeech
        tk.Checkbutton(row2, text="Category (categoria) -> partOfSpeech", variable=self.include_category).pack(side=tk.LEFT, padx=10) 
        # Type (tipus) -> termType
        tk.Checkbutton(row2, text="Type (tipus) -> termType", variable=self.include_type).pack(side=tk.LEFT, padx=10) 
        # Hierarchy (jerarquia) -> normativeAuthorization
        tk.Checkbutton(row2, text="Hierarchy (jerarquia) -> normativeAuthorization", variable=self.include_hierarchy).pack(side=tk.LEFT, padx=10)


        # ------------------- Filter Frame -------------------
        filter_frame = tk.LabelFrame(master, text="Denomination Filters (Applied to Principal SL Term)", padx=15, pady=10, font=self.bold_font)
        filter_frame.pack(fill='x', pady=10)
        
        filter_frame.columnconfigure(1, weight=1) # Allow the entry field to expand

        # Category Filter
        tk.Label(filter_frame, text="Category Prefixes (e.g., 'n', 'v', 'adj'):").grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.category_starts, width=60).grid(row=0, column=1, padx=5, pady=2, sticky='ew')
        
        # Type Filter
        tk.Label(filter_frame, text="Term Type Filters (e.g., 'principal', 'equivalent'):").grid(row=1, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.type_filter, width=60).grid(row=1, column=1, padx=5, pady=2, sticky='ew')
        
        # Hierarchy Filter
        tk.Label(filter_frame, text="Hierarchy Filters (e.g., 'terme pral.', 'sigla'):").grid(row=2, column=0, sticky='w', pady=2)
        tk.Entry(filter_frame, textvariable=self.hierarchy_filter, width=60).grid(row=2, column=1, padx=5, pady=2, sticky='ew')
        
        tk.Label(filter_frame, text="Separators: comma, space, or newline. All filters are case-insensitive.", font=('Helvetica', 9, 'italic')).grid(row=3, column=0, columnspan=2, sticky='w', pady=5)
        
        # ------------------- Process Button and Log -------------------
        
        tk.Button(master, 
                  text="EXECUTE CONVERSION (TO TBX)", 
                  command=self.run_conversion, 
                  font=self.bold_font,
                  bg='#2980b9', fg='white', 
                  activebackground='#3498db', activeforeground='white',
                  relief=tk.RAISED,
                  padx=10, pady=5).pack(fill='x', pady=15)

        tk.Label(master, text="Operation Log:", anchor='w').pack(fill='x')
        self.log_text = scrolledtext.ScrolledText(master, height=10, state='disabled', wrap=tk.WORD, font=('Courier New', 10), bg='#f0f0f0')
        self.log_text.pack(fill='both', expand=True)

    def browse_input(self):
        """Opens the dialog to select the input XML file."""
        filename = filedialog.askopenfilename(
            defaultextension=".xml",
            title="Select Input XML Glossary File",
            filetypes=[("XML Glossary Files", "*.xml"), ("All files", "*.*")]
        )
        if filename:
            self.input_file.set(filename)

    def browse_output(self):
        """Opens the dialog to select the output TBX file."""
        filename = filedialog.asksaveasfilename(
            # IMPORTANT: Default extension changed to .tbx
            defaultextension=".tbx", 
            title="Save Output TBX Termbase File",
            filetypes=[
                # File type label updated to .tbx
                ("TBX Termbase Files", "*.tbx"), 
                ("XML Files", "*.xml"),
                ("All files", "*.*")
            ],
            # IMPORTANT: No initial filename set
            initialfile="" 
        )
        if filename:
            self.output_file.set(filename)

    def log(self, message, message_type='info'):
        """Writes a message to the log area with color coding."""
        self.log_text.config(state='normal')
        
        # Color mapping
        tag_map = {'info': '#0055A4', 'error': '#C0392B', 'success': '#27AE60'} 
        
        # Configure tags the first time
        if not hasattr(self.log_text, 'tag_configured_flag'):
            for msg_type, color in tag_map.items():
                self.log_text.tag_config(msg_type, foreground=color)
            self.log_text.tag_config('bold', font=('Courier New', 10, 'bold'))
            setattr(self.log_text, 'tag_configured_flag', True)

        # Apply tags
        tags_to_apply = ('bold', message_type) if message_type == 'success' else (message_type,)

        # Remove markdown from messages
        clean_message = message.replace('**', '') 
        self.log_text.insert(tk.END, clean_message + '\n', tags_to_apply)
        self.log_text.yview(tk.END)
        self.log_text.config(state='disabled')
        
        self.master.update_idletasks() # Force GUI update

    def run_conversion(self):
        """Executes the conversion with user data."""
        # Clear the log
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # Check mandatory fields
        if not self.input_file.get() or not self.output_file.get() or not self.sl_code.get() or not self.tl_code.get():
            self.log("ERROR: All File Paths and Language Codes are mandatory.", 'error')
            return

        try:
            # Call the main conversion function
            xml_to_tbx(
                input_file=self.input_file.get(),
                output_file=self.output_file.get(),
                sl=self.sl_code.get().strip().lower(),
                tl=self.tl_code.get().strip().lower(),
                # Inclusion
                include_area=self.include_area.get(),
                include_definition=self.include_definition.get(),
                include_category=self.include_category.get(),
                include_type=self.include_type.get(),
                include_hierarchy=self.include_hierarchy.get(),
                # Filters
                category_starts=self.category_starts.get(),
                type_filter=self.type_filter.get(),
                hierarchy_filter=self.hierarchy_filter.get(),
                log_func=self.log # Pass the GUI logging function
            )
        except Exception as e:
            # Capture any unhandled exception from the conversion logic
            self.log(f"A critical error interrupted the process: {e}", 'error')

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry("800x850") 
    app = XML2TBX_App(root)
    root.mainloop()
