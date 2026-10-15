using System;
using System.Drawing;
using System.Diagnostics;
using System.Windows.Forms;
namespace ZapretManager {
public class AboutForm:Form {
 public AboutForm(){Text="О zaper";Size=new Size(590,380);MinimumSize=Size;MaximumSize=Size;StartPosition=FormStartPosition.CenterParent;Padding=new Padding(28);var panel=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false};panel.Controls.Add(new Label {Text="zaper",Width=500,Height=55,Name="brand"});panel.Controls.Add(new Label {Text="Версия 3.8.0\r\nУправление подключением, профилями и диагностикой.",Width=500,Height=62});panel.Controls.Add(new Label {Text="MIT License · ivanmorkovka1-ux\r\nЛицензии сторонних компонентов находятся в папке licenses.",Width=500,Height=62});var source=new LinkLabel {Text="Исходный код на GitHub",AutoSize=true,LinkColor=UiTheme.Accent};source.LinkClicked+=(s,e)=>Process.Start(new ProcessStartInfo("https://github.com/ivanmorkovka1-ux/zaper2") {UseShellExecute=true});panel.Controls.Add(source);var close=new Button {Text="Закрыть",Width=140,Margin=new Padding(0,16,0,0)};close.Click+=(s,e)=>Close();panel.Controls.Add(close);Controls.Add(panel);UiTheme.Apply(this);panel.Controls[0].Font=new Font("Segoe UI",27,FontStyle.Bold);source.LinkColor=UiTheme.Accent;Icon=TrayController.CreateIcon(UiTheme.Accent);}
}
}
