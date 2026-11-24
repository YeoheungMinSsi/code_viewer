namespace Study;
public interface IEntity { }
public class Note : IEntity {
    public Note() { }
    public string Describe() => "학습 메모";
    public string Format(int count) => "메모 " + count;
    public string Format(string title) => title;
}
