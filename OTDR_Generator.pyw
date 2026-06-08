"""
OTDR PDF Generator — double-click to run (no console)
Auto-installs required packages on first run.
"""
import os
import io
import glob
import threading
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

REQUIRED = ["pyotdr", "reportlab", "matplotlib"]

def _check_and_install():
    """Check for missing packages; install them with a progress window if needed."""
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return True

    # Show install window
    win = tk.Tk()
    win.title("OTDR PDF Generator — Setup")
    win.resizable(False, False)
    win.configure(bg='#F0F4FF')

    tk.Label(win, text="กำลัง install dependencies...",
             font=('Helvetica', 12, 'bold'), bg='#1565C0', fg='white',
             padx=16, pady=10).pack(fill='x')

    tk.Label(win, text=f"ต้องการ: {', '.join(missing)}",
             font=('Helvetica', 9), bg='#F0F4FF', pady=6).pack()

    status_var = tk.StringVar(value="เริ่ม install...")
    tk.Label(win, textvariable=status_var, font=('Courier', 8),
             bg='#F0F4FF', wraplength=380, justify='left',
             padx=12).pack(fill='x')

    pbar = ttk.Progressbar(win, mode='indeterminate', length=380)
    pbar.pack(padx=12, pady=(4, 12))
    pbar.start(10)

    win.update()
    win.geometry(f"+{win.winfo_screenwidth()//2-200}+{win.winfo_screenheight()//2-100}")

    success = [True]

    def do_install():
        try:
            for pkg in missing:
                status_var.set(f"pip install {pkg} ...")
                win.update()
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    success[0] = False
                    status_var.set(f"Error: {result.stderr[:200]}")
                    win.update()
                    return
            status_var.set("เสร็จแล้ว!")
            win.update()
        except Exception as e:
            success[0] = False
            status_var.set(f"Error: {e}")
            win.update()
        finally:
            pbar.stop()
            win.after(800, win.destroy)

    threading.Thread(target=do_install, daemon=True).start()
    win.mainloop()

    if not success[0]:
        tk.Tk().withdraw()
        messagebox.showerror("Install Failed",
            f"ไม่สามารถ install ได้\nลองรัน cmd แล้วพิมพ์:\n"
            f"pip install {' '.join(missing)}")
        sys.exit(1)

    return True


_check_and_install()

# ── lazy imports (may take a moment on first run) ──
def _import_heavy():
    global matplotlib, plt, np, read, colors, A4, mm, \
           getSampleStyleSheet, ParagraphStyle, TA_CENTER, \
           SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, \
           Image, PageBreak, HRFlowable
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from pyotdr import read
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, HRFlowable
    )


# ══════════════════════════════════════════════
#  Core logic (copied from generate_pdf.py)
# ══════════════════════════════════════════════

def parse_sor(filepath):
    status, results, tracedata = read.sorparse(filepath)
    return (results, tracedata) if status == "ok" else (None, None)


def trace_to_arrays(tracedata):
    distances, levels = [], []
    for line in tracedata:
        parts = line.strip().split('\t')
        if len(parts) == 2:
            try:
                distances.append(float(parts[0]))
                levels.append(float(parts[1]))
            except ValueError:
                pass
    import numpy as np
    return np.array(distances), np.array(levels)


def get_fiber_length(key_events):
    n = key_events.get('num events', 0)
    last = key_events.get(f'event {n}', {})
    dist = last.get('distance', None)
    if dist is None:
        return '-'
    try:
        km = float(dist)
        return f'{km:.3f} km ({km*1000:.0f} m)'
    except ValueError:
        return str(dist)


def get_events_table_data(key_events):
    rows = [['#', 'Distance (km)', 'Type', 'Splice Loss (dB)', 'Refl Loss (dB)', 'Slope (dB/km)']]
    for k, v in key_events.items():
        if not k.startswith('event'):
            continue
        ev_type = v.get('type', '')
        short_type = ('Reflection' if 'reflection' in ev_type.lower()
                      else 'End of Fiber' if 'end' in ev_type.lower()
                      else ev_type[:20])
        rows.append([k.replace('event ', ''), v.get('distance', '-'), short_type,
                     v.get('splice loss', '-'), v.get('refl loss', '-'), v.get('slope', '-')])
    return rows


def make_trace_image(distances, levels, events, fiber_num, wavelength):
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(7, 2), dpi=100)
    if len(distances) > 0:
        ax.plot(distances, levels, color='#1565C0', linewidth=0.8, alpha=0.9)
        ax.set_xlim(0, max(distances) * 1.02 if max(distances) > 0 else 1)
        valid = [l for l in levels if l > 0]
        ymin = (min(valid) - 2) if valid else 0
        ymax = (max(valid) + 3) if valid else 40
        ax.set_ylim(ymin, ymax)
        for ev_key, ev in events.items():
            if not ev_key.startswith('event'):
                continue
            try:
                d = float(ev.get('distance', 0))
                if 0 < d <= max(distances):
                    ax.axvline(x=d, color='red', linewidth=0.7, linestyle='--', alpha=0.6)
            except (ValueError, TypeError):
                pass
    ax.set_xlabel('Distance (km)', fontsize=7)
    ax.set_ylabel('Level (dB)', fontsize=7)
    ax.set_title(f'Fiber #{fiber_num:02d}  |  {wavelength}', fontsize=8, fontweight='bold')
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.tick_params(labelsize=6)
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def build_pdf(sor_files, output_pdf, project_name, progress_cb):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, HRFlowable
    )

    W, H = A4
    doc = SimpleDocTemplate(output_pdf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    TBL_HEADER = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1565C0')),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 8),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME',   (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',   (0,1), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#EEF2FF')]),
        ('GRID',       (0,0), (-1,-1), 0.4, colors.HexColor('#CCCCCC')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ])

    info_style = TableStyle([
        ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTNAME',  (4,0), (4,-1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0,0), (-1,-1), 7.5),
        ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#1565C0')),
        ('TEXTCOLOR', (2,0), (2,-1), colors.HexColor('#1565C0')),
        ('TEXTCOLOR', (4,0), (4,-1), colors.HexColor('#1565C0')),
        ('VALIGN',    (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.HexColor('#F5F5F5')]),
        ('LINEBELOW', (0,0), (-1,-1), 0.3, colors.HexColor('#DDDDDD')),
        ('LEFTPADDING',  (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
    ])

    summ_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0D47A1')),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME',   (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,-1), 8),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#E3F2FD')),
        ('GRID',       (0,0), (-1,-1), 0.4, colors.HexColor('#CCCCCC')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ])

    style_title  = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=18, alignment=TA_CENTER, spaceAfter=4)
    style_sub    = ParagraphStyle('s', fontName='Helvetica', fontSize=11, alignment=TA_CENTER, spaceAfter=2, textColor=colors.grey)
    style_fhdr   = ParagraphStyle('fh', fontName='Helvetica-Bold', fontSize=10, spaceBefore=0, spaceAfter=1, textColor=colors.HexColor('#0D47A1'))
    style_evhdr  = ParagraphStyle('eh', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#1565C0'), spaceBefore=1, spaceAfter=1)

    story = []

    # ── Cover ──
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph("OTDR TEST REPORT", style_title))
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width="80%", thickness=2, color=colors.HexColor('#1565C0'), hAlign='CENTER'))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(f"Project: {project_name}", style_sub))
    story.append(Paragraph(f"Total Fibers: {len(sor_files)}", style_sub))
    story.append(Spacer(1, 10*mm))

    # Summary table
    summary_rows = [['Fiber', 'Wavelength', 'Fiber Length', 'Test Range', 'Pulse', 'Avg Time', 'Total Loss (dB)']]
    all_data = []
    for i, fpath in enumerate(sor_files):
        progress_cb(f"Reading {i+1}/{len(sor_files)}: {os.path.basename(fpath)}")
        results, tracedata = parse_sor(fpath)
        all_data.append((results, tracedata))
        if results is None:
            summary_rows.append([f'#{i+1:02d}', 'ERROR', '-', '-', '-', '-', '-'])
            continue
        gp = results.get('GenParams', {})
        fp = results.get('FxdParams', {})
        ke = results.get('KeyEvents', {})
        total_loss = ke.get('Summary', {}).get('total loss', 0.0)
        summary_rows.append([
            f'#{i+1:02d}',
            gp.get('wavelength', '-'),
            get_fiber_length(ke),
            f"{fp.get('acquisition range distance', '-')} m",
            fp.get('pulse width', '-'),
            fp.get('averaging time', '-'),
            f'{total_loss:.3f}' if isinstance(total_loss, float) else str(total_loss),
        ])

    summary_tbl = Table(summary_rows, colWidths=[14*mm, 20*mm, 38*mm, 20*mm, 18*mm, 18*mm, 24*mm], repeatRows=1)
    summary_tbl.setStyle(TBL_HEADER)
    story.append(summary_tbl)
    story.append(PageBreak())

    # ── Per-fiber pages (2 per page) ──
    def fiber_block(fiber_num, results, tracedata, fname):
        block = []
        if results is None:
            block.append(Paragraph(f"Fiber #{fiber_num:02d} — Parse Error", style_fhdr))
            return block
        gp = results.get('GenParams', {})
        sp = results.get('SupParams', {})
        fp = results.get('FxdParams', {})
        ke = results.get('KeyEvents', {})

        wav = gp.get('wavelength', '-')
        dt  = fp.get('date/time', '-')
        if '(' in dt:
            dt = dt.split('(')[0].strip()

        block.append(Paragraph(f"Fiber #{fiber_num:02d}  —  {wav}  |  {dt}", style_fhdr))
        block.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#1565C0')))
        block.append(Spacer(1, 1*mm))

        res_str = (f"{fp.get('resolution',0):.5f} m"
                   if isinstance(fp.get('resolution'), float) else '-')
        info_data = [
            ['Wavelength', wav,
             'Pulse',     fp.get('pulse width', '-'),
             'Range',     f"{fp.get('acquisition range distance','-')} m"],
            ['Fiber Type', gp.get('fiber type', '-'),
             'Avg Time',  fp.get('averaging time', '-'),
             'Ref Index', fp.get('index', '-')],
            ['Location A', gp.get('location A', '-').strip() or '-',
             'Location B', gp.get('location B', '-').strip() or '-',
             'Resolution', res_str],
        ]
        info_tbl = Table(info_data, colWidths=[20*mm, 38*mm, 18*mm, 26*mm, 20*mm, 30*mm])
        info_tbl.setStyle(info_style)
        block.append(info_tbl)
        block.append(Spacer(1, 1.5*mm))

        distances, levels = trace_to_arrays(tracedata)
        img_buf = make_trace_image(distances, levels, ke, fiber_num, wav)
        block.append(Image(img_buf, width=170*mm, height=50*mm))
        block.append(Spacer(1, 1.5*mm))

        block.append(Paragraph("Key Events", style_evhdr))
        ev_rows = get_events_table_data(ke)
        ev_tbl  = Table(ev_rows, colWidths=[10*mm, 26*mm, 42*mm, 30*mm, 30*mm, 28*mm])
        ev_tbl.setStyle(TBL_HEADER)
        block.append(ev_tbl)
        block.append(Spacer(1, 1.5*mm))

        summ = ke.get('Summary', {})
        summ_data = [
            ['Total Loss (dB)', 'ORL (dB)', 'Loss Start (km)', 'Loss End (km)'],
            [f"{summ.get('total loss', 0.0):.3f}",
             f"{summ.get('ORL', 0.0):.3f}",
             f"{summ.get('loss start', 0.0):.3f}",
             f"{summ.get('loss end', 0.0):.3f}"],
        ]
        summ_tbl = Table(summ_data, colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
        summ_tbl.setStyle(summ_style)
        block.append(summ_tbl)
        return block

    for i, (results, tracedata) in enumerate(all_data):
        fiber_num = i + 1
        progress_cb(f"Rendering fiber {fiber_num}/{len(sor_files)}...")
        story.extend(fiber_block(fiber_num, results, tracedata, os.path.basename(sor_files[i])))
        if fiber_num < len(sor_files):
            if fiber_num % 2 == 0:
                story.append(PageBreak())
            else:
                story.append(Spacer(1, 3*mm))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CCCCCC')))
                story.append(Spacer(1, 3*mm))

    progress_cb("Writing PDF...")
    doc.build(story)


# ══════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OTDR PDF Generator")
        self.resizable(False, False)
        self.configure(bg='#F0F4FF')

        PAD = dict(padx=12, pady=6)

        # ── header ──
        tk.Label(self, text="OTDR PDF Generator",
                 font=('Helvetica', 16, 'bold'), bg='#1565C0', fg='white',
                 anchor='w', padx=12, pady=10).pack(fill='x')

        # ── source section ──
        frm_src = tk.LabelFrame(self, text=" Source ", bg='#F0F4FF',
                                font=('Helvetica', 9, 'bold'), padx=8, pady=6)
        frm_src.pack(fill='x', **PAD)

        self.src_var = tk.StringVar(value="(ยังไม่ได้เลือก)")

        tk.Label(frm_src, textvariable=self.src_var, bg='#F0F4FF',
                 font=('Courier', 9), anchor='w', width=55,
                 relief='sunken', padx=4).grid(row=0, column=0, columnspan=2,
                                               sticky='ew', pady=(0,6))

        tk.Button(frm_src, text="📁  เลือกโฟลเดอร์",
                  command=self.pick_folder, width=18,
                  bg='#1565C0', fg='white', font=('Helvetica', 9, 'bold'),
                  relief='flat', cursor='hand2').grid(row=1, column=0, padx=(0,6))

        tk.Button(frm_src, text="📄  เลือกไฟล์ .sor",
                  command=self.pick_files, width=18,
                  bg='#1976D2', fg='white', font=('Helvetica', 9, 'bold'),
                  relief='flat', cursor='hand2').grid(row=1, column=1)

        self.file_count = tk.StringVar(value="")
        tk.Label(frm_src, textvariable=self.file_count,
                 bg='#F0F4FF', font=('Helvetica', 8), fg='#555').grid(
                     row=2, column=0, columnspan=2, sticky='w', pady=(4,0))

        # ── output section ──
        frm_out = tk.LabelFrame(self, text=" Output PDF ", bg='#F0F4FF',
                                font=('Helvetica', 9, 'bold'), padx=8, pady=6)
        frm_out.pack(fill='x', **PAD)

        self.out_var = tk.StringVar(value="(กำหนดอัตโนมัติเมื่อเลือก source)")
        tk.Label(frm_out, textvariable=self.out_var, bg='#F0F4FF',
                 font=('Courier', 9), anchor='w', width=55,
                 relief='sunken', padx=4).grid(row=0, column=0, sticky='ew', pady=(0,4))

        tk.Button(frm_out, text="เปลี่ยน...",
                  command=self.pick_output, width=10,
                  bg='#607D8B', fg='white', font=('Helvetica', 9),
                  relief='flat', cursor='hand2').grid(row=0, column=1, padx=(6,0))

        # ── project name ──
        frm_proj = tk.LabelFrame(self, text=" Project Name ", bg='#F0F4FF',
                                 font=('Helvetica', 9, 'bold'), padx=8, pady=6)
        frm_proj.pack(fill='x', **PAD)
        self.proj_var = tk.StringVar(value="OTDR Test")
        tk.Entry(frm_proj, textvariable=self.proj_var, font=('Helvetica', 10),
                 width=40).pack(fill='x')

        # ── progress ──
        self.progress_var = tk.StringVar(value="พร้อมใช้งาน")
        tk.Label(self, textvariable=self.progress_var,
                 bg='#F0F4FF', font=('Helvetica', 8), fg='#444',
                 anchor='w', padx=12).pack(fill='x')

        self.pbar = ttk.Progressbar(self, mode='indeterminate', length=400)
        self.pbar.pack(fill='x', padx=12, pady=(0,4))

        # ── generate button ──
        self.btn_gen = tk.Button(self, text="▶  สร้าง PDF",
                                 command=self.generate,
                                 bg='#2E7D32', fg='white',
                                 font=('Helvetica', 12, 'bold'),
                                 relief='flat', cursor='hand2',
                                 padx=20, pady=8)
        self.btn_gen.pack(pady=8)

        self.btn_open = tk.Button(self, text="🗂  เปิด PDF",
                                  command=self.open_pdf,
                                  bg='#E65100', fg='white',
                                  font=('Helvetica', 10, 'bold'),
                                  relief='flat', cursor='hand2',
                                  padx=16, pady=6, state='disabled')
        self.btn_open.pack(pady=(0, 12))

        self._sor_files = []
        self._output_pdf = None
        self._libs_loaded = False

        # pre-load heavy libs in background
        threading.Thread(target=self._preload, daemon=True).start()

    def _preload(self):
        try:
            _import_heavy()
            self._libs_loaded = True
            self.progress_var.set("พร้อมใช้งาน")
        except Exception as e:
            self.progress_var.set(f"Import error: {e}")

    def _set_source(self, files, folder_label):
        self._sor_files = sorted(files)
        self.src_var.set(folder_label[:60])
        self.file_count.set(f"พบ {len(files)} ไฟล์ .sor")
        # auto output path — use folder name as filename
        out_dir = os.path.dirname(files[0]) if files else os.getcwd()
        out_name = os.path.basename(out_dir) + ".pdf"
        self._output_pdf = os.path.join(out_dir, out_name)
        self.out_var.set(self._output_pdf[:70])

    def pick_folder(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์ที่มีไฟล์ .sor")
        if not folder:
            return
        files = sorted(glob.glob(os.path.join(folder, '*.sor')))
        if not files:
            messagebox.showwarning("ไม่พบไฟล์", "ไม่มีไฟล์ .sor ในโฟลเดอร์นี้")
            return
        # auto project name from folder
        self.proj_var.set(os.path.basename(folder))
        self._set_source(files, folder)

    def pick_files(self):
        files = filedialog.askopenfilenames(
            title="เลือกไฟล์ .sor",
            filetypes=[("SOR files", "*.sor"), ("All files", "*.*")]
        )
        if not files:
            return
        self._set_source(list(files), f"{len(files)} ไฟล์ที่เลือก")

    def pick_output(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์ปลายทาง")
        if not folder:
            return
        fname = os.path.basename(self._output_pdf) if self._output_pdf else "output.pdf"
        self._output_pdf = os.path.join(folder, fname)
        self.out_var.set(self._output_pdf[:70])

    def open_pdf(self):
        if self._output_pdf and os.path.exists(self._output_pdf):
            os.startfile(self._output_pdf)

    def generate(self):
        if not self._sor_files:
            messagebox.showwarning("ยังไม่ได้เลือก", "เลือกโฟลเดอร์หรือไฟล์ .sor ก่อน")
            return
        if not self._output_pdf:
            messagebox.showwarning("ยังไม่มี output path", "กำหนด output PDF path ก่อน")
            return

        self.btn_gen.config(state='disabled')
        self.btn_open.config(state='disabled')
        self.pbar.start(10)

        def run():
            try:
                if not self._libs_loaded:
                    self.progress_var.set("กำลัง load libraries...")
                    _import_heavy()
                    self._libs_loaded = True

                build_pdf(
                    self._sor_files,
                    self._output_pdf,
                    self.proj_var.get(),
                    lambda msg: self.progress_var.set(msg),
                )
                self.after(0, self._on_done)
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_done(self):
        self.pbar.stop()
        self.btn_gen.config(state='normal')
        self.btn_open.config(state='normal')
        self.progress_var.set(f"เสร็จแล้ว → {os.path.basename(self._output_pdf)}")
        messagebox.showinfo("สำเร็จ", f"PDF สร้างเสร็จแล้ว\n{self._output_pdf}")

    def _on_error(self, msg):
        self.pbar.stop()
        self.btn_gen.config(state='normal')
        self.progress_var.set(f"Error: {msg}")
        messagebox.showerror("Error", msg)


if __name__ == '__main__':
    app = App()
    app.mainloop()
