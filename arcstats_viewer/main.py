# arcstats_viewer/main.py

import gi
import subprocess
import threading
from datetime import datetime

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas

# --- Constants for sysctl keys ---
ARCSTATS_PREFIX = "kstat.zfs.misc.arcstats"
ARC_HITS = f"{ARCSTATS_PREFIX}.hits"
ARC_MISSES = f"{ARCSTATS_PREFIX}.misses"
ARC_SIZE = f"{ARCSTATS_PREFIX}.size"
LOW_RATIO_THRESHOLD = 90  # Hit ratio below this is considered "low"

def human_readable(n, unit='B'):
    """Converts a number to a human-readable format (e.g., KB, MB, GB)."""
    for x in ['', 'K', 'M', 'G', 'T']:
        if abs(n) < 1024.0:
            return f"{n:3.1f} {x}{unit}"
        n /= 1024.0
    return f"{n:.1f} P{unit}"

class ArcStatsViewer(Gtk.Window):
    """
    The main application window for displaying ZFS ARC statistics.
    """
    def __init__(self):
        super().__init__(title="ZFS ARC Stats Viewer")
        self.set_default_size(1000, 700)
        self.set_border_width(10)

        self.numeric_stats = {}
        self.history = []
        self.last_output = ""
        self.last_update_time = None

        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        self.build_table_view()
        self.build_chart_view()

        # Initial load and schedule periodic refresh
        self.refresh_stats()
        GLib.timeout_add_seconds(5, self.refresh_stats)

    def build_table_view(self):
        """Builds the primary tab with the stats table and controls."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_entry = Gtk.Entry(placeholder_text="Filter ARC stat keys...")
        self.search_entry.connect("changed", self.on_search_changed)
        
        self.refresh_label = Gtk.Label(label="Loading initial data...")
        self.unit_toggle = Gtk.CheckButton(label="Human-readable units")
        self.unit_toggle.set_active(True)
        self.unit_toggle.connect("toggled", self.on_unit_toggled)

        hbox.pack_start(Gtk.Label(label="Search:"), False, False, 0)
        hbox.pack_start(self.search_entry, True, True, 0)
        hbox.pack_start(self.unit_toggle, False, False, 0)
        hbox.pack_start(self.refresh_label, False, False, 0)
        vbox.pack_start(hbox, False, False, 0)

        self.store = Gtk.ListStore(str, str)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self.filter_func)
        
        self.tree = Gtk.TreeView(model=self.filtered)
        self.add_column("Key", 0)
        self.add_column("Value", 1)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(self.tree)
        frame = Gtk.Frame(label="ARC Statistics Table")
        frame.add(scroll)
        vbox.pack_start(frame, True, True, 0)

        self.summary_label = Gtk.Label(label="Summary will appear here.")
        # Enable Pango markup parsing for the summary label
        self.summary_label.set_use_markup(True)
        summary_frame = Gtk.Frame(label="Summary")
        summary_frame.add(self.summary_label)
        vbox.pack_start(summary_frame, False, False, 0)

        self.notebook.append_page(vbox, Gtk.Label(label="Stats Table"))

    def build_chart_view(self):
        """Builds the secondary tab with the history chart."""
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        
        chart_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        chart_box.pack_start(self.canvas, True, True, 0)
        self.notebook.append_page(chart_box, Gtk.Label(label="Hits & Misses Chart"))

    def update_chart(self):
        """Redraws the chart with the latest history data."""
        if not self.history:
            return

        times = range(-len(self.history) + 1, 1)
        hits = [point['hits'] for point in self.history]
        misses = [point['misses'] for point in self.history]
        ratios = [point['ratio'] for point in self.history]

        self.ax.clear()
        
        # Twin the axis for the ratio plot
        ax2 = self.ax.twinx()
        ax2.set_ylabel("Hit Ratio (%)", color="green")
        ax2.tick_params(axis='y', labelcolor="green")
        ax2.set_ylim(0, 101)

        # Plot data
        self.ax.plot(times, hits, label="Hits", marker='o', linestyle='-')
        self.ax.plot(times, misses, label="Misses", marker='o', linestyle='-')
        ax2.plot(times, ratios, label="Hit Ratio (%)", color="green", marker='x', linestyle='--')

        # --- IMPROVED LEGEND HANDLING ---
        # Get handles and labels from both axes
        handles1, labels1 = self.ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()

        # Combine them and create a single legend in the best location
        self.ax.legend(handles1 + handles2, labels1 + labels2, loc='best')
        
        self.ax.set_title("ARC Hits, Misses, and Hit Ratio")
        self.ax.set_xlabel("Time (5-second intervals)")
        self.ax.set_ylabel("Count")
        self.figure.tight_layout()
        self.canvas.draw()

    def add_column(self, title, col_id):
        """Adds a column to the TreeView."""
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(title, renderer, text=col_id)
        column.set_sort_column_id(col_id)
        self.tree.append_column(column)

    def filter_func(self, model, iter, data):
        """Filters the table based on the search entry."""
        text = self.search_entry.get_text().lower()
        return text in model[iter][0].lower()

    def on_search_changed(self, widget):
        """Handler for the search entry's 'changed' signal."""
        self.filtered.refilter()

    def on_unit_toggled(self, widget):
        """Updates the table values when the unit toggle is changed."""
        GLib.idle_add(self.update_store, self.last_output, self.last_update_time)

    def refresh_stats(self):
        """Initiates a background thread to reload ARC stats."""
        self.refresh_label.set_text("🔄 Refreshing...")
        thread = threading.Thread(target=self.load_arcstats, daemon=True)
        thread.start()
        return True

    def load_arcstats(self):
        """
        Fetches ARC stats using sysctl in a background thread.
        """
        try:
            output = subprocess.check_output(
                ["sysctl", "kstat.zfs.misc.arcstats"], universal_newlines=True
            )
            update_time = datetime.now()
            GLib.idle_add(self.update_store, output, update_time)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            error_message = f"Error fetching stats: {e}"
            GLib.idle_add(self.update_ui_on_error, error_message)

    def update_ui_on_error(self, error_message):
        """Displays an error message in the UI."""
        self.refresh_label.set_text("Update failed")
        self.summary_label.set_text(error_message)

    def update_store(self, output, update_time):
        """
        Parses sysctl output and updates the table, summary, and chart.
        """
        self.last_output = output
        self.last_update_time = update_time
        self.store.clear()
        self.numeric_stats.clear()

        for line in output.splitlines():
            if ": " in line:
                key, val_str = line.split(": ", 1)
                key = key.strip()
                val_str = val_str.strip()
                try:
                    num_val = int(val_str)
                    self.numeric_stats[key] = num_val
                    display_val = human_readable(num_val) if self.unit_toggle.get_active() else f"{num_val:,}"
                except ValueError:
                    display_val = val_str
                self.store.append([key, display_val])
        
        self.update_summary()
        if update_time:
            self.refresh_label.set_text(f"Updated: {update_time.strftime('%H:%M:%S')}")
        return False

    def update_summary(self):
        """Calculates and displays summary statistics."""
        size = self.numeric_stats.get(ARC_SIZE, 0)
        hits = self.numeric_stats.get(ARC_HITS, 0)
        misses = self.numeric_stats.get(ARC_MISSES, 0)
        total = hits + misses
        ratio = (hits / total * 100) if total > 0 else 0.0

        size_disp = human_readable(size) if self.unit_toggle.get_active() else f"{size:,} B"
        summary_text = f"ARC Size: {size_disp}    Hits: {hits:,}    Misses: {misses:,}    Hit Ratio: {ratio:.2f}%"
        
        # Use Pango markup for color instead of CSS class
        if ratio < LOW_RATIO_THRESHOLD and ratio > 0:
            summary_markup = f"<span foreground='orange' font_weight='bold'>{summary_text}</span>"
        else:
            summary_markup = summary_text

        self.summary_label.set_markup(summary_markup)

        # Update history for the chart
        self.history.append({'hits': hits, 'misses': misses, 'ratio': ratio})
        if len(self.history) > 60:
            self.history.pop(0)
        self.update_chart()

def main():
    """Initializes and runs the GTK application."""
    app = ArcStatsViewer()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()
