namespace Study.Tools;
public static class NoteExtensions {
    public static string Summary(this Study.Note note) => "메모 요약";
    public static T Keep<T>(this T value) where T : class, Study.IEntity, new() => value;
}
