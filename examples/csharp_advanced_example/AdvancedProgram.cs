using Study;
using Study.Tools;
class AdvancedProgram {
    static void Main() {
        var note = new Note();
        note.Summary();
        note.Keep();
        dynamic dynamicNote = new Note();
        dynamicNote.Describe();
        var method = typeof(Note).GetMethod("Format", new[] { typeof(int) });
        method.Invoke(note, new object[] { 2 });
        typeof(Note).GetMethod("Describe").Invoke(note, null);
    }
}
