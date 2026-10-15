using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Net;
using System.Drawing;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
namespace ZapretManager {
public static class HostsEditor {
 public static string SystemPath {get{return Path.Combine(Environment.SystemDirectory,"drivers\\etc\\hosts");}}
 public static int Validate(string text){int count=0;int number=0;foreach(string raw in Regex.Split(text,@"\r?\n")){number++;string line=raw.Split('#')[0].Trim();if(line=="")continue;var parts=Regex.Split(line,@"\s+");IPAddress ip;if(parts.Length<2||!IPAddress.TryParse(parts[0],out ip)||parts.Skip(1).Any(p=>!Regex.IsMatch(p,@"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$")))throw new Exception("Строка "+number+": ожидается IP и имя узла, например 127.0.0.1 localhost");count++;}return count;}
 public static string Save(string path,string expected,string text){Validate(text);if(File.ReadAllText(path)!=expected)throw new IOException("Hosts изменён другой программой. Откройте окно заново, чтобы не потерять изменения.");string backup=Core.PathOf("hosts-backup-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,6)+".txt");File.Copy(path,backup);try{File.WriteAllText(path,text,new UTF8Encoding(false));}catch{try{File.Copy(backup,path,true);}catch{}throw;}return backup;}
}
public class HostsForm:Form {
 readonly TextBox editor=new TextBox {Multiline=true,AcceptsReturn=true,AcceptsTab=true,ScrollBars=ScrollBars.Both,WordWrap=false,Dock=DockStyle.Fill};readonly Label info=new Label {Dock=DockStyle.Bottom,Height=58};CancellationTokenSource stop=new CancellationTokenSource();string original;bool busy;
 public HostsForm(){Text="Hosts";Size=new Size(900,670);MinimumSize=new Size(700,500);StartPosition=FormStartPosition.CenterParent;Padding=new Padding(20);original=File.ReadAllText(HostsEditor.SystemPath);editor.Text=original;var title=new Label {Text="Системный файл Hosts",Font=new Font("Segoe UI",18,FontStyle.Bold),Dock=DockStyle.Top,Height=48};var hint=new Label {Text="Изменяйте записи вручную или загрузите предложенные. Загрузка меняет только текст в этом окне; запись на диск — кнопкой «Сохранить».",Dock=DockStyle.Top,Height=58};var actions=new FlowLayoutPanel {Dock=DockStyle.Bottom,Height=62,Padding=new Padding(0,8,0,0)};var load=new Button {Text="Загрузить предложенные",AutoSize=true};var save=new Button {Text="Сохранить",AutoSize=true};var cancel=new Button {Text="Закрыть",AutoSize=true};actions.Controls.AddRange(new Control[]{load,save,cancel});Controls.Add(editor);Controls.Add(hint);Controls.Add(title);Controls.Add(info);Controls.Add(actions);UiTheme.Apply(this);title.Font=new Font("Segoe UI",18,FontStyle.Bold);editor.Font=new Font("Consolas",10);UiTheme.Primary(save);info.Text="Перед сохранением создаётся резервная копия. Комментарии и пустые строки разрешены.";
  load.Click+=async(s,e)=>{if(busy||!Core.OperationGate.Wait(0)){info.Text="Дождитесь завершения текущей операции.";return;}busy=true;load.Enabled=save.Enabled=false;try{Core.Guard();string update=await Downloads.Fetch("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/hosts",stop.Token);editor.Text=Core.MergeHosts(editor.Text,update);info.Text="Предложенные записи загружены. Проверьте текст и сохраните, когда будете готовы.";}catch(OperationCanceledException){info.Text="Загрузка отменена.";}catch(Exception ex){info.Text=ex.Message;}finally{busy=false;load.Enabled=save.Enabled=true;stop.Dispose();stop=new CancellationTokenSource();Core.OperationGate.Release();}};
  save.Click+=async(s,e)=>{if(busy||!Core.OperationGate.Wait(0)){info.Text="Дождитесь завершения текущей операции.";return;}busy=true;load.Enabled=save.Enabled=false;try{Core.Guard();string backup=HostsEditor.Save(HostsEditor.SystemPath,original,editor.Text);original=editor.Text;var result=await Core.Run(Path.Combine(Environment.SystemDirectory,"ipconfig.exe"),"/flushdns",stop.Token);info.Text="Hosts сохранён. Копия: "+Path.GetFileName(backup)+(result.Exit==0?". DNS-кэш очищен.":". DNS-кэш не очищен: "+result.Exit);}catch(Exception ex){info.Text="Не удалось сохранить: "+ex.Message;}finally{busy=false;load.Enabled=save.Enabled=true;stop.Dispose();stop=new CancellationTokenSource();Core.OperationGate.Release();}};
  cancel.Click+=(s,e)=>Close();FormClosing+=(s,e)=>{if(busy){stop.Cancel();e.Cancel=true;info.Text="Отмена. Дождитесь завершения операции.";}};FormClosed+=(s,e)=>stop.Dispose();
 }
}
}
