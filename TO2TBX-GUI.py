import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

# Add the 'xml' namespace for 'xml:lang'
ET.register_namespace('xml', "http://www.w3.org/XML/1998/namespace")

# Function to indent (pretty print) an ElementTree, compatible with Python < 3.9
def indent(elem, level=0, space="  "):
    """
    Format the XML tree for readability (simulating pretty print).
    Based on standard library implementation details.
    """
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

# --- CORE CONVERSION LOGIC (TBX) ---

def xml_to_tbx_core(input_file, output_file, sl, tl, include_area, include_definition):
    """
    Core function to convert an XML glossary file into a TermBase eXchange (TBX) file.
    
    Returns True on success, or an error string on failure.
    """
    try:
        # Load and parse the XML file
        tree = ET.parse(input_file)
        root = tree.getroot()

    except FileNotFoundError:
        return f"Error: Input file '{input_file}' not found."
    except ET.ParseError:
        return f"Error: Input file '{input_file}' is not a valid XML."
    except Exception as e:
        return f"An unexpected error occurred during XML parsing: {e}"

    # --- 1. TBX Structure Setup ---
    
    TBX_NS = "urn:iso:std:iso:4466:tbx:v1"
    ET.register_namespace('', TBX_NS) 
    
    martif = ET.Element(
        'martif', 
        {
            'type': "TBX", 
            '{http://www.w3.org/XML/1998/namespace}lang': sl.lower()
        }
    )
    
    # Create the <martifHeader>
    martif_header = ET.SubElement(martif, 'martifHeader')
    file_desc = ET.SubElement(martif_header, 'fileDesc')
    title_stmt = ET.SubElement(file_desc, 'titleStmt')
    ET.SubElement(title_stmt, 'title').text = f"TBX Conversion from {input_file}"
    
    source_desc = ET.SubElement(file_desc, 'sourceDesc')
    ET.SubElement(source_desc, 'p').text = f"Generated from XML source on {datetime.now().strftime('%Y-%m-%d')}"
    
    encoding_desc = ET.SubElement(martif_header, 'encodingDesc')
    ET.SubElement(encoding_desc, 'p').text = "Using TBX-min structure."

    text = ET.SubElement(martif, 'text')
    body = ET.SubElement(text, 'body')
    
    
    # --- 2. Data Processing and TBX Generation ---
    
    entry_counter = 0

    # Iterate over each <fitxa> (glossary entry)
    for entry in root.findall('.//fitxa'):
        entry_counter += 1
        
        area_tematica = entry.findtext('areatematica', default='').strip()
        
        terms_sl = []
        terms_tl = []
        definitions_sl = []
        
        # Collect terms
        for denomination in entry.findall('denominacio'):
            language = denomination.get('llengua')
            term = denomination.findtext('.', default='').strip()
            if language == sl:
                terms_sl.append(term)
            elif language == tl:
                terms_tl.append(term)
        
        # Collect definitions
        if include_definition:
            for definition in entry.findall('definicio'):
                language = definition.get('llengua')
                if language == sl:
                    text_definition = definition.findtext('.', default='').strip().replace('\n', ' ')
                    definitions_sl.append(text_definition)
        
        if not terms_sl:
            continue

        if include_definition:
            if not definitions_sl:
                definitions_sl.append('') 
        else:
            definitions_sl.append(None) 
            
        if not terms_tl:
            terms_tl.append('')

        # Create a <termEntry> for every definition/sense
        for i, definition_sl in enumerate(definitions_sl):
            
            term_entry = ET.SubElement(body, 'termEntry', {'id': f"e-{entry_counter}-{i+1}"})

            # Thematic Area (Subject)
            if include_area and area_tematica:
                subject_desc = ET.SubElement(term_entry, 'descrip', {'type': "subject"})
                subject_desc.text = area_tematica

            # Language Section for SL
            lang_sec_sl = ET.SubElement(term_entry, 'langSet', {'xml:lang': sl})
            
            # Terms and Definitions for SL
            for term_sl in terms_sl:
                if not term_sl: continue
                tig = ET.SubElement(lang_sec_sl, 'tig')
                ET.SubElement(tig, 'term').text = term_sl
                
                if include_definition and definition_sl is not None and definition_sl:
                    def_desc = ET.SubElement(tig, 'descrip', {'type': "definition"})
                    def_desc.text = definition_sl
            
            # Language Section for TL
            lang_sec_tl = ET.SubElement(term_entry, 'langSet', {'xml:lang': tl})
            
            # Terms for TL
            for term_tl in terms_tl:
                if not term_tl: continue
                tig = ET.SubElement(lang_sec_tl, 'tig')
                ET.SubElement(tig, 'term').text = term_tl
    
    # --- 3. Write TBX File ---
    try:
        # Indent the whole tree for readability
        indent(martif) 
        
        # Create an ElementTree object
        output_tree = ET.ElementTree(martif)
        
        # Write the file without 'pretty_print'
        output_tree.write(
            output_file, 
            encoding='UTF-8', 
            xml_declaration=True
        )

        return True # Success

    except IOError:
        return f"Error: Could not write to the output file '{output_file}'. Check permissions or path."
    except Exception as e:
        return f"An unexpected error occurred during file writing: {e}"


# --- TKINTER GUI INTERFACE ---

class GlossaryConverterApp:
    def __init__(self, master):
        self.master = master
        master.title("XML to TBX Glossary Converter")

        # Control Variables (Default values set)
        self.input_path = tk.StringVar(value="")
        self.output_path = tk.StringVar(value="")
        self.sl_code = tk.StringVar(value="ca")
        self.tl_code = tk.StringVar(value="es")
        self.include_area = tk.BooleanVar(value=False)
        self.include_definition = tk.BooleanVar(value=False)

        # Build the interface
        self.create_widgets()

    def create_widgets(self):
        # Set style for better appearance
        self.master.option_add('*TButton.highlightThickness', 0)
        
        # 1. File Selection Frame (Buttons on the left)
        file_frame = tk.LabelFrame(self.master, text="File Selection", padx=10, pady=10)
        file_frame.pack(padx=10, pady=10, fill="x")
        
        # Input File 
        tk.Button(file_frame, text="Select Input XML", command=self.browse_input, width=20).grid(row=0, column=0, padx=(5, 5), pady=5)
        tk.Entry(file_frame, textvariable=self.input_path, width=50).grid(row=0, column=1, padx=(0, 5), pady=5, sticky="ew")
        
        # Output File 
        tk.Button(file_frame, text="Select Output TBX", command=self.browse_output, width=20).grid(row=1, column=0, padx=(5, 5), pady=5)
        tk.Entry(file_frame, textvariable=self.output_path, width=50).grid(row=1, column=1, padx=(0, 5), pady=5, sticky="ew")
        
        # Make the Entry field column expand horizontally
        file_frame.grid_columnconfigure(1, weight=1)


        # 2. Language Codes Frame
        lang_frame = tk.LabelFrame(self.master, text="Language Codes (e.g., ca, es, en)", padx=10, pady=10)
        lang_frame.pack(padx=10, pady=10, fill="x")

        # SL Input
        tk.Label(lang_frame, text="Source Language (SL):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(lang_frame, textvariable=self.sl_code, width=10).grid(row=0, column=1, padx=5, pady=5)

        # TL Input
        tk.Label(lang_frame, text="Target Language (TL):").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        tk.Entry(lang_frame, textvariable=self.tl_code, width=10).grid(row=0, column=3, padx=5, pady=5)

        # 3. Options Frame
        options_frame = tk.LabelFrame(self.master, text="Data Options (Both Recommended)", padx=10, pady=10)
        options_frame.pack(padx=10, pady=10, fill="x")

        # Checkbox Thematic Area
        tk.Checkbutton(options_frame, text="Include Thematic Area (<descrip type=\"subject\">)", variable=self.include_area).pack(anchor="w", pady=2)

        # Checkbox Definition
        tk.Checkbutton(options_frame, text="Include Definition (SL) (<descrip type=\"definition\">)", variable=self.include_definition).pack(anchor="w", pady=2)

        # 4. Conversion Button
        tk.Button(self.master, text="CONVERT TO TBX", command=self.run_conversion, height=2, 
                  bg="#007bff", fg="white", font=('Arial', 10, 'bold')).pack(fill="x", padx=10, pady=10)

    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="Select Input XML File",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        if filename:
            self.input_path.set(filename)

    def browse_output(self):
        # Default extension is set to .tbx
        filename = filedialog.asksaveasfilename(
            title="Save Output TBX File",
            defaultextension=".tbx", 
            filetypes=[("TBX files", "*.tbx"), ("All files", "*.*")]
        )
        if filename:
            self.output_path.set(filename)

    def run_conversion(self):
        # 1. Get parameters and validate
        input_file = self.input_path.get()
        output_file = self.output_path.get()
        sl = self.sl_code.get().strip().lower()
        tl = self.tl_code.get().strip().lower()
        
        if not all([input_file, output_file, sl, tl]):
            messagebox.showerror("Parameter Error", "Please fill in all required fields (Files and Language Codes).")
            return
        
        if sl == tl:
            messagebox.showwarning("Warning", "Source and Target language codes are the same. Continuing with conversion.")

        # 2. Run the core logic
        result = xml_to_tbx_core(
            input_file,
            output_file,
            sl,
            tl,
            self.include_area.get(),
            self.include_definition.get()
        )

        # 3. Show result
        if result is True:
            # Ensure the output file has .tbx extension for the message
            final_output_file = self.output_path.get()
            if not final_output_file.lower().endswith('.tbx'):
                final_output_file += '.tbx'
                
            messagebox.showinfo("Conversion Complete", f"✅ TBX Conversion successful!\nFile saved to: {final_output_file}")
        else:
            messagebox.showerror("Conversion Error", result)


# --- MAIN APPLICATION ENTRY POINT ---

if __name__ == "__main__":
    root = tk.Tk()
    app = GlossaryConverterApp(root)
    root.mainloop()
