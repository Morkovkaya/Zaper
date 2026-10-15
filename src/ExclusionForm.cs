using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows.Forms;
namespace ZapretManager {
public class ExclusionForm:Form {
 readonly ListBox list=new ListBox {Dock=DockStyle.Fill,HorizontalScrollbar=true,SelectionMode=SelectionMode.MultiExtended};
 readonly CheckBox enabled=new CheckBox {Text="Включить исключения",Checked=true,AutoSize=true};
 readonly Label state=new Label {Dock=DockStyle.Bottom,Height=54};
 readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer {Interval=1000};
 bool busy;string notice;FlowLayoutPanel controls;
 public ExclusionForm(){Text="Zaper — исключения приложений";Size=new Size(980,620);MinimumSize=new Size(700,400);StartPosition=FormStartPosition.CenterParent;BackColor=Color.FromArgb(18,21,25);ForeColor=Color.White;Font=new Font("Segoe UI",10);Padding=new Padding(15);list.BackColor=Color.FromArgb(30,35,42);list.ForeColor=Color.White;controls=new FlowLayoutPanel {Dock=DockStyle.Top,Height=155};controls.Controls.Add(enabled);Button("Добавить EXE",()=>{using(var f=new OpenFileDialog {Title="Выберите приложения, которые будут обходить zapret 2",Filter="Приложения (*.exe)|*.exe",Multiselect=true})if(f.ShowDialog(this)==DialogResult.OK)Add(f.FileNames);});Button("Выбрать приложение",()=>new AppPicker(paths=>{Add(paths);state.Text="Приложения добавлены. Нажмите «Сохранить».";}).Show(this));Button("Добавить Steam",()=>{var files=Exclusions.Steam();if(files.Length==0){state.Text="Steam не найден. Выберите steam.exe вручную.";return;}Add(files);state.Text="Добавлены Steam и найденные steamwebhelper.exe. Нажмите «Сохранить».";});Button("Удалить выбранные",()=>{foreach(var item in list.SelectedItems.Cast<string>().ToArray())list.Items.Remove(item);});Button("Сохранить",async()=>await Save());var info=new Label {Dock=DockStyle.Top,Height=100,Text="Выбранные EXE обходят обработку zapret 2. Остальные приложения сохраняют текущую стратегию.\nSteam добавляется вместе с его веб-процессом. Другие дочерние EXE добавляйте отдельно.\nПри VPN/proxy внешний трафик может принадлежать процессу VPN: исключение исходного EXE\nне меняет маршрут VPN. Не добавляйте VPN в исключения ради одного приложения."};Controls.Add(list);Controls.Add(info);Controls.Add(controls);Controls.Add(state);var c=Exclusions.Load();enabled.Checked=c.Enabled;Add(c.Applications??new string[0]);UiTheme.Apply(this);timer.Tick+=(s,e)=>RefreshStatus();timer.Start();RefreshStatus();FormClosing+=(s,e)=>{if(busy){e.Cancel=true;return;}timer.Dispose();};}
 void Button(string title,Action click){var b=new Button {Text=title,AutoSize=true,Height=35,FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(42,47,54),ForeColor=Color.White};b.Click+=(s,e)=>{notice=null;click();};controls.Controls.Add(b);}
 void Add(string[] paths){foreach(string p in paths){string full=Exclusions.Normalize(p);if(!list.Items.Cast<string>().Contains(full,StringComparer.OrdinalIgnoreCase))list.Items.Add(full);}}
 async Task Save(){if(busy||!Core.OperationGate.Wait(0)){state.Text="Дождитесь завершения операции в другом окне.";return;}busy=true;controls.Enabled=list.Enabled=false;timer.Stop();state.Text="Сохранение и подтверждение исключений…";try{var c=new ExclusionConfig {Enabled=enabled.Checked,Applications=list.Items.Cast<string>().ToArray()};await Task.Run(()=>Exclusions.Save(c));notice="Сохранено. "+(Core.State()=="Running"?"Исключения применены.":"Применятся при включении zapret 2.");}catch(Exception e){notice="Ошибка: "+e.Message;}finally{Core.OperationGate.Release();busy=false;controls.Enabled=list.Enabled=true;RefreshStatus();timer.Start();}}
 void RefreshStatus(){try{string s="Служба исключений: "+Exclusions.State();if(File.Exists(Core.PathOf("app-exclusions-status.json"))){var h=Core.Read<ExclusionHealth>(Core.PathOf("app-exclusions-status.json"));s+=" | пакетов в обход: "+h.Bypassed+" | обычный путь: "+h.Processed;if(h.Error!="")s+="\n"+h.Error;else if(h.Warning!="")s+="\n"+h.Warning;}state.Text=notice==null?s:notice+"\n"+s;}catch(Exception e){state.Text=e.Message;}}
}
}
