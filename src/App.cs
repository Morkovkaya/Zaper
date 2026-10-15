using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Diagnostics;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Collections.Generic;

namespace ZapretManager {
static class Program {
 public static bool UiTesting,TestStartupPreferences;
 [System.Runtime.InteropServices.DllImport("user32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode)]static extern IntPtr FindWindow(string cls,string name);
 [System.Runtime.InteropServices.DllImport("user32.dll")]static extern bool SetForegroundWindow(IntPtr window);
 [System.Runtime.InteropServices.DllImport("user32.dll")]static extern bool ShowWindow(IntPtr window,int show);
 [STAThread]static int Main(string[] args){try{UiTesting=args.Contains("--ui-test");
  if(args.Length>1&&args[0]=="--test-ux"){return RevisionTests.Run(args[1],args.Contains("--online")).GetAwaiter().GetResult();}
  if(args.Length>1&&args[0]=="--test-convenience"){return ConvenienceTests.Run(args[1],args.Contains("--integration")).GetAwaiter().GetResult();}
  if(args.Length>1&&args[0]=="--prepare-target"){Core.Root=Path.GetFullPath(args[1]);if(Directory.Exists(Core.Root))Package.Prepare();return 0;}
  if(args.Length>0&&args[0]=="--enable-faceit-compat"){Network.FaceitUdpPreset(true,CancellationToken.None).GetAwaiter().GetResult();return 0;}
  if(args.Length>1&&args[0]=="--test-faceit-preset"){return FaceitPresetTests.Run(args[1]).GetAwaiter().GetResult();}
  if(args.Length>1&&args[0]=="--test-save-exclusions"){return SaveExclusionTests.Run(args[1]).GetAwaiter().GetResult();}
  if(args.Length>1&&args[0]=="--repair-check"){return RepairTests.Run(args[1]).GetAwaiter().GetResult();}
  if(args.Length>0&&args[0]=="--check-runtime"){Core.Preflight();return 0;}
  if(args.Length>0&&args[0]=="--test-canonical-helper"){Core.Service="zapret2-repair-test";Exclusions.ServiceName="zapret2-repair-helper-test";Exclusions.Testing=true;Exclusions.Ensure().GetAwaiter().GetResult();return 0;}
  if(args.Contains("--engine-service")){System.ServiceProcess.ServiceBase.Run(new EngineService(args.Length>1?args[1]:"zapret2"));return 0;}
  if(args.Contains("--prepare-package")){Package.Prepare();return 0;}
  if(args.Contains("--exclusion-service")){if(args.Length>1)Exclusions.ServiceName=args[1];ExclusionWorker.TestMode=Exclusions.ServiceName.EndsWith("-test",StringComparison.OrdinalIgnoreCase);System.ServiceProcess.ServiceBase.Run(new ExclusionService());return 0;}
  if(args.Contains("--exclusion-worker")){ExclusionWorker.TestMode=true;using(var stop=new CancellationTokenSource()){if(args.Length>1)stop.CancelAfter(int.Parse(args[1]));ExclusionWorker.Run(stop.Token);}return 0;}
  if(args.Contains("--test-exclusions")){return ExclusionTests.Run(args[1]).GetAwaiter().GetResult();}
  if(args.Contains("--exclusion-probe")){ExclusionTests.SendProbe();return 0;}
  if(args.Contains("--exclusion-probe-tcp")){ExclusionTests.SendTcpProbe();return 0;}
  if(args.Length>0&&args[0]=="--test-package-service"){Package.TestService().GetAwaiter().GetResult();return 0;}if(args.Length>0&&args[0]=="--configure-package"){Package.Configure().GetAwaiter().GetResult();return 0;} if(args.Length>0&&args[0]=="--uninstall-package"){Package.Remove().GetAwaiter().GetResult();return 0;} if(args.Length>0&&args[0]=="--package-check"){return Tests.Run(new[]{args[1],""}).GetAwaiter().GetResult();} if(args.Length>0&&args[0]=="--relay"){Relay.Serve(int.Parse(args[1]));return 0;}if(args.Length>0&&args[0]=="--watch"){Relay.Watch(int.Parse(args[1]));return 0;}if(args.Length>0&&args[0]=="--recover-proxy"){Relay.Recover();return 0;}
  if(args.Length>0&&args[0]=="--self-test"){return Tests.Run(args.Skip(1).ToArray()).GetAwaiter().GetResult();}
  if(args.Contains("--ui-test")){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);return UiRegression.Run().GetAwaiter().GetResult();}
  bool preview=args.Contains("--preview");if(!preview&&!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)){Process.Start(new ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location){UseShellExecute=true,Verb="runas",Arguments=string.Join(" ",args.Select(Core.Quote))});return 0;}
  using(var mutex=new Mutex(false,@"Local\Zapret2NativeManager")){bool own=false;try{try{own=mutex.WaitOne(0);}catch(AbandonedMutexException){own=true;}if(!own){IntPtr window=FindWindow(null,"zaper 3.8.0");if(window!=IntPtr.Zero){ShowWindow(window,9);SetForegroundWindow(window);}return 0;}Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new MainForm(preview,args.Contains("--tray")));}finally{if(own)mutex.ReleaseMutex();}}return 0;
 }catch(Exception e){if(args.Any(a=>a=="--test-convenience"||a=="--enable-faceit-compat"||a=="--test-faceit-preset"||a=="--test-save-exclusions"||a=="--check-runtime"||a=="--test-canonical-helper"||a=="--repair-check"||a=="--prepare-target"||a=="--engine-service"||a=="--exclusion-service"||a=="--prepare-package"||a=="--exclusion-worker"||a=="--configure-package"||a=="--uninstall-package"||a=="--test-package-service")){File.WriteAllText(Core.PathOf("package-error.txt"),e.ToString());return 1;}if(args.Contains("--self-test")){File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"fatal-test.txt"),e.ToString());}else MessageBox.Show(e.Message,"Zapret 2 — ошибка",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}}
}
public class MainForm:Form {
 FlowLayoutPanel panel=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false,AutoScroll=true,Padding=new Padding(18)};Control uploadTitle,uploadRow;
 readonly Label status=new Label(),context=new Label(),strategy=new Label();readonly TextBox log=new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Height=145};readonly ProgressBar progress=new ProgressBar {Height=20};readonly ComboBox game=new ComboBox(),ips=new ComboBox(),discord=new ComboBox(),gameFake=new ComboBox();readonly ComboBox udpPreset=new ComboBox();readonly CheckBox faceEx=new CheckBox {Text="Учитывать исключения IP серверов FACEIT",Width=390};readonly CheckBox auto=new CheckBox {Text="Автозапуск с Windows"},check=new CheckBox {Text="Проверять обновления при открытии"};readonly NumericUpDown rate=new NumericUpDown {Minimum=1,Maximum=100,Value=17,Width=65};readonly List<Control> changes=new List<Control>();readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer {Interval=1500};CancellationTokenSource cancellation;bool busy;bool preview;readonly bool startHidden;bool firstVisibility;public readonly LatencyPanel NetworkGraph=new LatencyPanel();
 public MainForm(bool previewMode=false,bool forceTray=false){
  preview=previewMode;startHidden=forceTray||(!preview&&(!Program.UiTesting||Program.TestStartupPreferences)&&Convenience.Preferences().StartInTray);Text="zaper 3.8.0";Size=new Size(1100,820);MinimumSize=new Size(960,700);StartPosition=FormStartPosition.CenterScreen;AutoScaleMode=AutoScaleMode.Dpi;BackColor=UiTheme.Background;ForeColor=UiTheme.Text;Font=new Font("Segoe UI",10);
  var sidebar=new FlowLayoutPanel {Dock=DockStyle.Left,Width=205,FlowDirection=FlowDirection.TopDown,WrapContents=false,Padding=new Padding(18,26,18,18),BackColor=UiTheme.Surface};
  sidebar.Controls.Add(new Label {Text="zaper",Name="brand",Width=165,Height=48});
  sidebar.Controls.Add(new Label {Text="Управление подключением",Width=165,Height=52,ForeColor=UiTheme.Muted});
  var content=new Panel {Dock=DockStyle.Fill,Padding=new Padding(22,20,22,12)};
  var journal=new Panel {Dock=DockStyle.Bottom,Height=164,Padding=new Padding(22,0,22,14)};
  log.Dock=DockStyle.Fill;log.Font=new Font("Consolas",9);var journalTitle=new Label {Text="Журнал операций",Dock=DockStyle.Top,Height=28};progress.Dock=DockStyle.Bottom;progress.Height=5;journal.Controls.Add(log);journal.Controls.Add(journalTitle);journal.Controls.Add(progress);
  Controls.Add(content);Controls.Add(journal);Controls.Add(sidebar);
  Action<string> page=name=>{
   panel=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false,AutoScroll=true,Padding=new Padding(0)};
   pages.Add(panel);content.Controls.Add(panel);var target=panel;
   var nav=new Button {Text=name,Width=165,Height=45,TextAlign=ContentAlignment.MiddleLeft,Margin=new Padding(0,3,0,3)};
   navigation.Add(nav);sidebar.Controls.Add(nav);nav.Click+=(s,e)=>SelectPage(pages.IndexOf(target));
   panel.SizeChanged+=(s,e)=>{foreach(Control c in target.Controls)c.Width=Math.Max(350,target.ClientSize.Width-24);};
   Header(name);
  };
  page("Главная");
  Add(new Label {Text="Включайте zapret и выбирайте режим для игр и Discord.",Height=28,ForeColor=UiTheme.Muted});
  status.Height=45;Add(status);strategy.Height=32;Add(strategy);context.Height=35;Add(context);
  var on=Button("Включить zapret",()=>Service("On"));on.Name="primary";
  Row(on,Button("Выключить",()=>Service("Off")),Button("Перезапустить",()=>Service("Restart")));
  Header("Быстрый доступ");
  Row(Button("Профили подключения",()=>new ProfileForm().Show(this)),Button("История и откат",()=>new HistoryForm(path=>Do(async tk=>{await Convenience.RestoreHistory(path,tk);Log("Копия из истории восстановлена");})).Show(this)));
  Row(Button("Исключения приложений",()=>new ExclusionForm().Show(this)));
  Header("Автоподбор стратегии");
  Add(new Label {Text="Проверит варианты подключения и сохранит лучший результат.",Height=28,ForeColor=UiTheme.Muted});
  Row(Button("Начать подбор",Tune),Button("Отменить",()=>{if(cancellation!=null){cancellation.Cancel();Log("Запрошена отмена. Дождитесь отката.");}},false));
  Row(Button("Вернуть предыдущую",()=>Do(tk=>{Network.Recover();LoadSettings();Log("Предыдущая стратегия восстановлена");return Task.FromResult(0);})),Button("Результаты подбора",()=>ShowFile(Core.PathOf("native-autotune-results.json")),false));
  page("Настройки");
  Add(new Label {Text="Изменения вступят в силу после нажатия «Сохранить настройки».",Height=38,ForeColor=UiTheme.Muted});
  auto.Width=250;check.Width=350;Fill(game,new[]{"off","udp","tcp","all"});game.Name="game";Fill(ips,new[]{"none","loaded","any"});ips.Name="ips";
  string[] files=Directory.Exists(Core.PathOf("files"))?Directory.GetFiles(Core.PathOf("files"),"*.bin").Select(Path.GetFileName).OrderBy(s=>s).ToArray():new[]{"ACTIVE_DISCORD_UDP.bin","ACTIVE_GAME_UDP.bin"};Fill(discord,files);Fill(gameFake,files);
  Fill(udpPreset,new[]{"Стандартный","FACEIT: совместимость"});
  Row(Label("Игровой режим"),udpPreset);Row(faceEx);Row(auto);Row(check);
  var advanced=new List<Control>();Button expand=null;expand=Button("Дополнительные параметры  ▸",()=>{bool show=!advanced[0].Visible;foreach(var c in advanced)c.Visible=show;expand.Text=show?"Скрыть дополнительные параметры  ▾":"Дополнительные параметры  ▸";},false);Row(expand);
  Row(Label("Обработка игр"),game);advanced.Add(panel.Controls[panel.Controls.Count-1]);Row(Label("Область обработки"),ips);advanced.Add(panel.Controls[panel.Controls.Count-1]);Row(Label("Пакет Discord UDP"),discord);advanced.Add(panel.Controls[panel.Controls.Count-1]);Row(Label("Пакет игр UDP"),gameFake);advanced.Add(panel.Controls[panel.Controls.Count-1]);foreach(var c in advanced)c.Visible=false;
  var save=Button("Сохранить настройки",Apply);save.Name="primary";Row(save);
  changes.AddRange(new Control[]{game,ips,auto,check,discord,gameFake,udpPreset,faceEx});
  page("Диагностика");
  Add(new Label {Text="Проверьте сеть, доступность сервисов и задержку соединения.",Height=38,ForeColor=UiTheme.Muted});
  Row(Button("Проверить конфигурацию",Diagnostics),Button("Проверить сеть",NetworkTests));
  Row(Button("Соединение серверов",()=>new FaceForm().Show(this),false));
  NetworkGraph.Height=330;Add(NetworkGraph);
  Row(Button("Проверить и исправить",()=>Do(async tk=>Log(await Convenience.Repair(tk)))),Button("Экспорт диагностики",ExportDiagnostics,false));
  Header("Защита от задержек");
  uploadTitle=panel.Controls[panel.Controls.Count-1];
  Row(Label("Исходящая скорость"),rate,Label("Мбит/с"),Button("Включить лимит",Protect),Button("Выключить лимит",()=>Do(tk=>{Relay.Off();Log("Исходный proxy восстановлен");return Task.FromResult(0);})));uploadRow=panel.Controls[panel.Controls.Count-1];
  page("Обслуживание");
  Header("Обновления");
  Row(Button("Обновить список IP",()=>Do(async tk=>Log(await Core.UpdateIPs(tk)))),Button("Hosts",()=>new HostsForm().Show(this),false));
  Row(Button("Обновление приложения",()=>new UpdateForm().Show(this),false),Button("Обновление движка",()=>Do(async tk=>Log(await Core.Updates()))));
  Row(Button("Настройки трея",()=>new PreferencesForm(()=>Log("Настройки трея сохранены")).Show(this)),Button("О приложении",()=>new AboutForm().Show(this),false));
  Header("Служба Windows");
  Add(new Label {Text="Установка и удаление службы. Файлы и настройки сохраняются.",Height=38,ForeColor=UiTheme.Muted});
  Row(Button("Установить службу",()=>Do(async tk=>{await Core.Install(tk);Log("Служба установлена");})),Button("Удалить службу",()=>Do(async tk=>{await Core.Remove(tk);Log("Служба удалена; файлы сохранены");})));
  UiTheme.Apply(this);log.Font=new Font("Consolas",9);
  foreach(var p in pages)foreach(Control c in p.Controls)if(c.Name=="heading")c.Font=new Font("Segoe UI",17,FontStyle.Bold);
  sidebar.Controls[0].Font=new Font("Segoe UI",19,FontStyle.Bold);status.Font=new Font("Segoe UI",18,FontStyle.Bold);
  foreach(var p in pages)foreach(Control row in p.Controls)foreach(Control c in row.Controls)if(c.Name=="primary")UiTheme.Primary((Button)c);
  tray=new TrayController(this,Service);SelectPage(0);timer.Tick+=(s,e)=>RefreshState();timer.Start();LoadSettings();RefreshState();FormClosing+=Closing;
  Shown+=async(s,e)=>{if(preview){await Task.Delay(300);Tests.Preview(this);ExitApp();}else if(!Program.UiTesting&&check.Checked)await Do(async tk=>Log(await Core.Updates()));};
 }
 readonly List<FlowLayoutPanel> pages=new List<FlowLayoutPanel>();
 readonly List<Button> navigation=new List<Button>();TrayController tray;
 public void CapturePages(string directory){
  var report=new List<string>();int failures=0;Size original=Size;
  foreach(Size size in new[]{original,MinimumSize}){
   Size=size;
   for(int i=0;i<pages.Count;i++){
    SelectPage(i);PerformLayout();pages[i].PerformLayout();Application.DoEvents();if(i==1){foreach(Control row in pages[i].Controls)foreach(Control c in row.Controls){var button=c as Button;if(button!=null&&button.Text.StartsWith("Дополнительные параметры")){button.PerformClick();pages[i].PerformLayout();Application.DoEvents();}}}
    foreach(Control row in pages[i].Controls){var flow=row as FlowLayoutPanel;if(flow==null)continue;flow.PerformLayout();foreach(Control c in flow.Controls){if(c.Visible&&(c.Right>flow.ClientSize.Width||c.Bottom>flow.ClientSize.Height)){report.Add("FAIL: clipped control "+c.Text+" at "+size);failures++;}}}
    if(size==original)using(var bitmap=new Bitmap(Width,Height)){DrawToBitmap(bitmap,new Rectangle(Point.Empty,Size));bitmap.Save(Path.Combine(directory,"page-"+i+".png"));}
   }
  }
  foreach(Control row in pages[1].Controls)foreach(Control c in row.Controls){var button=c as Button;if(button!=null&&button.Text.StartsWith("Скрыть дополнительные"))button.PerformClick();}Size=original;SelectPage(0);report.Add("Failures: "+failures);File.WriteAllLines(Path.Combine(directory,"layout-test.txt"),report);
 }
 public void SelectPage(int index){for(int i=0;i<pages.Count;i++){pages[i].Visible=i==index;navigation[i].BackColor=i==index?UiTheme.Accent:UiTheme.Surface;}pages[index].BringToFront();}
 public void Log(string text){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(new Action<string>(Log),text);return;}string line="["+DateTime.Now.ToString("HH:mm:ss")+"] "+text+Environment.NewLine;log.AppendText(line);try{File.AppendAllText(Core.PathOf("native-manager.log"),line);}catch{}}
 void Add(Control c){c.Width=Math.Max(350,panel.ClientSize.Width-24);c.Margin=new Padding(0,0,0,8);panel.Controls.Add(c);}
 void Header(string t){Add(new Label {Text=t,Name="heading",Height=38,ForeColor=UiTheme.Text,Padding=new Padding(0,8,0,0)});}
 static Label Label(string t){return new Label {Text=t,Width=185,Height=40,TextAlign=ContentAlignment.MiddleLeft};}
 void Row(params Control[] controls){var row=new FlowLayoutPanel {AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,MinimumSize=new Size(0,48),WrapContents=true,Margin=new Padding(0,1,0,10)};foreach(var c in controls)row.Controls.Add(c);Add(row);}
 Button Button(string text,Action action,bool mutation=true){var b=new Button {Text=text,AutoSize=true,Height=42,MinimumSize=new Size(155,42),BackColor=Color.FromArgb(42,47,54),ForeColor=Color.White,FlatStyle=FlatStyle.Flat};b.Click+=(s,e)=>action();if(mutation)changes.Add(b);return b;}
 static void Fill(ComboBox c,string[] values){c.DropDownStyle=ComboBoxStyle.DropDownList;c.Width=330;c.Items.AddRange(values);c.BackColor=Color.FromArgb(42,47,54);c.ForeColor=Color.White;}
 protected override void SetVisibleCore(bool value){if(value&&!firstVisibility){firstVisibility=true;if(startHidden){if(!IsHandleCreated)CreateHandle();value=false;}}base.SetVisibleCore(value);}
 public bool StartedHidden {get{return startHidden&&!Visible&&IsHandleCreated;}}
 public void ExitApp(){tray.Exit();}
 public bool TrayReleased {get{return tray.Released;}}
 public bool TestTray(){bool result=tray.Test();RefreshState();return result;}
 public void ReloadSettings(){LoadSettings();RefreshState();}
 void LoadSettings(){var s=Core.Load();game.SelectedItem=s.Game;ips.SelectedItem=s.IPSet;discord.SelectedItem=s.DiscordFake;gameFake.SelectedItem=s.GameFake;udpPreset.SelectedIndex=s.GameUdpPreset=="alt12-exp"?1:0;faceEx.Checked=s.FaceitServerExclusions;auto.Checked=s.AutoStart;check.Checked=s.AutoCheck;}
 void RefreshState(){try{string state=Core.State();if(tray!=null)tray.Refresh(state,busy||Core.OperationGate.CurrentCount==0);status.Text=state=="Running"?"●  Zapret включён":state=="Stopped"?"●  Zapret выключен":state=="NotInstalled"?"Служба не установлена":"Состояние: "+state;status.ForeColor=state=="Running"?Color.FromArgb(52,211,153):UiTheme.Muted;strategy.Text="Стратегия: "+Core.Load().StrategyName;string c=Core.Context();context.Text=c;context.Visible=c!="";uploadTitle.Visible=uploadRow.Visible=Core.Proxy()!="";}catch(Exception e){status.Text=e.Message;}}
 async Task Do(Func<CancellationToken,Task> operation){if(busy||!Core.OperationGate.Wait(0)){Log("Дождитесь завершения текущей операции в главном окне или FACEIT");return;}busy=true;cancellation=new CancellationTokenSource();RefreshState();foreach(var c in changes)c.Enabled=false;try{await Task.Run(()=>operation(cancellation.Token));}catch(OperationCanceledException){Log("Операция отменена; изменения автоподбора отменены");}catch(Exception e){Log("Ошибка: "+e.Message);if(Convenience.Preferences().NotifyErrors)tray.NotifyError(e.Message);}finally{cancellation.Dispose();cancellation=null;busy=false;Core.OperationGate.Release();foreach(var c in changes)c.Enabled=true;LoadSettings();RefreshState();}}
 public void ApplyPreset(bool gaming){Do(async tk=>{await Core.Apply(Convenience.Preset(gaming),tk);Log("Применён профиль: "+(gaming?"Игры + Discord":"Обычный"));});}
 public void ApplySavedProfile(SavedProfile profile){Do(async tk=>Log(await Convenience.ImportProfile(profile,tk)));}
 void ExportDiagnostics(){using(var picker=new SaveFileDialog {Filter="Отчёт ZIP (*.zip)|*.zip",FileName="Zapret-Diagnostics-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".zip"})if(picker.ShowDialog(this)==DialogResult.OK){try{Convenience.ExportDiagnostics(picker.FileName);Log("Отчёт сохранён. Секреты и имена пользовательских каталогов скрыты. Проверьте архив перед отправкой.");}catch(Exception ex){Log("Не удалось экспортировать отчёт: "+ex.Message);}}}
 void Service(string mode){Do(t=>{Core.Guard();Core.Control(mode);Log("Служба: "+Core.State());return Task.FromResult(0);});}
 void Protect(){int selectedRate=(int)rate.Value;Do(async t=>{await Relay.On(selectedRate,t);Log("Лимит upload включён");});}
 void Apply(){var s=Core.Load();s.Game=(string)game.SelectedItem;s.IPSet=(string)ips.SelectedItem;s.DiscordFake=(string)discord.SelectedItem;s.GameFake=(string)gameFake.SelectedItem;s.GameUdpPreset=udpPreset.SelectedIndex==1?"alt12-exp":"native";s.FaceitServerExclusions=faceEx.Checked;s.AutoStart=auto.Checked;s.AutoCheck=check.Checked;Do(async t=>{await Core.Apply(s,t);Log("Настройки проверены winws2 и применены");});}
 void Diagnostics(){Do(async t=>{await Core.Validate(Core.Build(Core.Load()),t);Log("Конфигурация: PASS\nСлужба: "+Core.State());foreach(var f in new[]{"winws2.exe","WinDivert.dll","WinDivert64.sys","cygwin1.dll","lua\\zapret-lib.lua","lua\\zapret-antidpi.lua"})Log(f+": "+(File.Exists(Core.PathOf(f))?"PASS":"FAIL"));Log("Процессы: "+string.Join(", ",Process.GetProcessesByName("winws2").Select(p=>p.Id.ToString())));});}
 void NetworkTests(){Do(async t=>{await Core.Validate(Core.Build(Core.Load()),t);var m=await Network.Measure(2,t);Core.Write(Core.PathOf("native-network-results.json"),m);foreach(var s in m.Samples)Log(s.Target+": "+(s.Unknown?"не подтверждено":s.Success?"PASS":"FAIL")+" "+s.Seconds.ToString("0.000")+" с "+s.Error);});}
 void Tune(){Do(async t=>await Network.Tune(t,(p,m)=>{BeginInvoke(new Action(()=>progress.Value=p));Log(m);}));}
 void ShowFile(string path){if(File.Exists(path)){var f=new Form {Text="Результаты автоподбора",Size=new Size(1000,650),StartPosition=FormStartPosition.CenterParent};try{var candidates=Core.Read<List<Candidate>>(path);var g=new DataGridView {Dock=DockStyle.Fill,ReadOnly=true,AllowUserToAddRows=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill};g.DataSource=candidates.Select(c=>new {Стратегия=c.Name,Успешно=c.Measurement==null?"—":c.Measurement.Good+"/"+c.Measurement.Samples.Count,Обязательные=c.Measurement!=null&&c.Measurement.Valid?"Пройдены":"Не пройдены",Медиана_с=c.Measurement==null?0:Math.Round(c.Measurement.Median,3),P90_с=c.Measurement==null?0:Math.Round(c.Measurement.P90,3),Ошибка=c.Error??string.Join("; ",c.Measurement==null?new string[0]:c.Measurement.Samples.Where(s=>!s.Success).Select(s=>s.Target+": "+s.Error))}).ToList();f.Controls.Add(g);}catch(Exception ex){f.Controls.Add(new TextBox {Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,Text=ex.Message+Environment.NewLine+File.ReadAllText(path)});}UiTheme.Apply(f);f.Show(this);}else MessageBox.Show("Результатов пока нет");}
 void Closing(object sender,FormClosingEventArgs e){if(tray!=null&&tray.HideOnClose(e))return;if(e.CloseReason==CloseReason.WindowsShutDown||e.CloseReason==CloseReason.TaskManagerClosing){timer.Stop();return;}if(busy||Core.OperationGate.CurrentCount==0){e.Cancel=true;if(cancellation!=null)cancellation.Cancel();foreach(var f in OwnedForms.OfType<FaceForm>())f.Cancel();Log("Дождитесь завершения операции и отката, затем закройте окно");}else timer.Stop();}
}
public class FaceForm:Form {
 public void Cancel(){if(cancel!=null)cancel.Cancel();}
 readonly TextBox server=new TextBox {Width=240};readonly DataGridView grid=new DataGridView {Dock=DockStyle.Fill,ReadOnly=true,AllowUserToAddRows=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,BackgroundColor=Color.FromArgb(25,29,34)};readonly Label info=new Label {Dock=DockStyle.Bottom,Height=65};CancellationTokenSource cancel;bool busy;
 public FaceForm(){Text="zaper — соединение серверов";Size=new Size(1150,690);MinimumSize=new Size(850,500);StartPosition=FormStartPosition.CenterParent;Font=new Font("Segoe UI",10);var row=new FlowLayoutPanel {Dock=DockStyle.Top,Height=100,Padding=new Padding(16)};row.Controls.Add(new Label {Text="Сервер CS2 IP:порт",Width=180,Height=35});row.Controls.Add(server);AddButton(row,"Проверить",()=>Run(async t=>{string address=server.Text;info.Text="Проверяем регионы FACEIT, DNS, сайты и указанный сервер…";grid.DataSource=await Network.Faceit(address,t);info.Text="Проверка завершена. Отсутствие ICMP-ответа не доказывает блокировку игры. Допуск в матч проверяется в CS2.";}));grid.AutoGenerateColumns=false;foreach(string name in new[]{"Name","Address","Ping","Loss","Result"})grid.Columns.Add(new DataGridViewTextBoxColumn {DataPropertyName=name,HeaderText=name=="Name"?"Регион / сервис":name=="Address"?"Адрес":name=="Ping"?"Задержка":name=="Loss"?"ICMP без ответа":"Результат",FillWeight=name=="Result"?240:name=="Address"?190:90});Controls.Add(grid);Controls.Add(row);Controls.Add(info);info.Text="Регионы FACEIT, узлы Cloudflare и Google, сайты и произвольный сервер CS2. Поле IP:порт необязательно. HTTP-время не является игровым пингом.";UiTheme.Apply(this);info.Padding=new Padding(16,8,16,0);info.Height=90;FormClosing+=(s,e)=>{if(busy){e.Cancel=true;cancel.Cancel();info.Text="Отмена проверки. Закройте окно после завершения.";}};}
 void AddButton(FlowLayoutPanel row,string text,Action action){var b=new Button {Text=text,AutoSize=true,Height=34,BackColor=Color.FromArgb(42,47,54),ForeColor=Color.White,FlatStyle=FlatStyle.Flat};b.Click+=(s,e)=>action();row.Controls.Add(b);}
 async void Run(Func<CancellationToken,Task> task){if(busy||!Core.OperationGate.Wait(0)){info.Text="Дождитесь завершения текущей операции в приложении";return;}busy=true;cancel=new CancellationTokenSource();try{await task(cancel.Token);}catch(OperationCanceledException){info.Text="Проверка отменена";}catch(Exception e){info.Text="Ошибка: "+e.Message;}finally{busy=false;cancel.Dispose();cancel=null;Core.OperationGate.Release();}}
}
}
