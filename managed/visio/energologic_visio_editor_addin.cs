using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio Editor")]
[assembly: AssemblyVersion("0.3.1.0")]

namespace EnergoLogicVisioEditor
{
    internal sealed class GlueTarget
    {
        public int TargetId;
        public int Row;
        public string Endpoint;
    }

    internal sealed class CellInfo
    {
        public int AnchorId;
        public int BusId;
        public int BusTerminalId;
        public int Slot;
        public int ConnectionRow;
        public string Endpoint;
        public List<int> CoreIds = new List<int>();
        public List<int> MemberIds = new List<int>();
    }

    internal sealed class ConnectionPointInfo
    {
        public int ShapeId;
        public int Row;
        public double Xmm;
        public double Ymm;
        public double DistanceMm;
    }


    [ComVisible(true)]
    [Guid("3288CA38-4200-47CB-9BDA-665B51B90937")]
    [InterfaceType(ComInterfaceType.InterfaceIsDual)]
    public interface IEnergoLogicEditorApi
    {
        string ApiDuplicateLeft();
        string ApiDuplicateRight();
        string ApiMoveLeft();
        string ApiMoveRight();
        string ApiSelectCell();
        string ApiRepairGluePreview();
        string ApiRepairGlueApply();
        string ApiDoctor();
        string ApiShowPanel();
        string ApiExactOffset(double dxMm, double dyMm);
        string ApiAlignX();
        string ApiAlignY();
        string ApiBaseCopy(double bx, double by, double tx, double ty);
        string ApiBaseMove(double bx, double by, double tx, double ty);
        string ApiMeasurePitch();
        string ApiDistributePitch(double pitchMm);
        string ApiVersion();
    }

    [ComVisible(true)]
    [Guid("F2236480-88B8-42B3-AEC4-0707D59A14FC")]
    [ProgId("EnergoLogic.VisioEditorAddinV31")]
    [ClassInterface(ClassInterfaceType.AutoDual)]
    public sealed class Connect : IDTExtensibility2, IEnergoLogicEditorApi
    {
        private object _application;
        private object _addInInstance;
        private EditorForm _form;
        private CommandBar _bar;
        private CommandBarButton _toggleButton;
        private _CommandBarButtonEvents_ClickEventHandler _toggleHandler;
        private readonly Regex _glueRegex = new Regex(
            @"(?<target>[^!(),]+)!Connections(?:\.X(?<rowx>\d+)|\.(?<row>\d+)\.X)",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);
        private readonly Regex _connectionCellRegex = new Regex(
            @"^Connections(?:\.X(\d+)|\.(\d+)\.X)$",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);

        public void OnConnection(object Application, ext_ConnectMode ConnectMode, object AddInInst, ref Array custom)
        {
            _application = Application;
            _addInInstance = AddInInst;
            try { dynamic host = AddInInst; host.Object = this; } catch { }
            InstallToggleButton();
            ShowPanel();
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            try { if (_form != null && !_form.IsDisposed) _form.Close(); } catch { }
            _form = null;
            _toggleButton = null;
            _bar = null;
            try { if (_addInInstance != null) { dynamic host = _addInInstance; host.Object = null; } } catch { }
            _addInInstance = null;
            _application = null;
        }

        public void OnAddInsUpdate(ref Array custom) { }
        public void OnStartupComplete(ref Array custom) { }
        public void OnBeginShutdown(ref Array custom) { }

        private dynamic App
        {
            get
            {
                if (_application == null) throw new InvalidOperationException("Visio не подключён");
                return _application;
            }
        }

        private void InstallToggleButton()
        {
            dynamic app = App;
            CommandBars bars = (CommandBars)app.CommandBars;
            const string barName = "EnergoLogic";
            try { _bar = bars[barName]; }
            catch { _bar = bars.Add(barName, MsoBarPosition.msoBarTop, Missing.Value, true); }

            _toggleButton = null;
            for (int i = 1; i <= _bar.Controls.Count; i++)
            {
                CommandBarControl c = _bar.Controls[i];
                if (String.Equals(c.Tag, "EnergoLogic.Editor.Toggle", StringComparison.Ordinal))
                {
                    _toggleButton = c as CommandBarButton;
                    break;
                }
            }
            if (_toggleButton == null)
                _toggleButton = (CommandBarButton)_bar.Controls.Add(MsoControlType.msoControlButton, Missing.Value, Missing.Value, Missing.Value, true);

            _toggleButton.Caption = "EnergoLogic";
            _toggleButton.Tag = "EnergoLogic.Editor.Toggle";
            _toggleButton.Style = MsoButtonStyle.msoButtonCaption;
            _toggleButton.TooltipText = "Показать панель EnergoLogic";
            _toggleButton.Visible = true;
            _toggleHandler = new _CommandBarButtonEvents_ClickEventHandler(OnToggleClick);
            _toggleButton.Click += _toggleHandler;
            _bar.Visible = true;
        }

        private void OnToggleClick(CommandBarButton Ctrl, ref bool CancelDefault)
        {
            CancelDefault = false;
            ShowPanel();
        }

        public void ShowPanel()
        {
            if (_form == null || _form.IsDisposed)
                _form = new EditorForm(this);
            if (!_form.Visible) _form.Show();
            _form.BringToFront();
            _form.Activate();
        }

        public string ApiDuplicateLeft() { return DuplicateCell(-1); }
        public string ApiDuplicateRight() { return DuplicateCell(1); }
        public string ApiMoveLeft() { return MoveCell(-1); }
        public string ApiMoveRight() { return MoveCell(1); }
        public string ApiSelectCell() { return SelectCell(); }
        public string ApiRepairGluePreview() { return RepairGlue(true, false); }
        public string ApiRepairGlueApply() { return RepairGlue(false, false); }
        public string ApiDoctor() { return Doctor(); }
        public string ApiShowPanel() { ShowPanel(); return "✓ Панель EnergoLogic показана."; }
        public string ApiExactOffset(double dxMm, double dyMm) { return ExactOffset(dxMm, dyMm); }
        public string ApiAlignX() { return Align("x"); }
        public string ApiAlignY() { return Align("y"); }
        public string ApiBaseCopy(double bx, double by, double tx, double ty) { return BasePointTransform(true, bx, by, tx, ty); }
        public string ApiBaseMove(double bx, double by, double tx, double ty) { return BasePointTransform(false, bx, by, tx, ty); }
        public string ApiMeasurePitch() { return MeasurePitch(); }
        public string ApiDistributePitch(double pitchMm) { return DistributePitch(pitchMm); }
        public string ApiVersion() { return "0.3.1"; }

        internal string DuplicateCell(int direction)
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            dynamic sourceTerminal = page.Shapes.ItemFromID(cell.BusTerminalId);
            dynamic targetTerminal = GetBusTerminalBySlot(page, cell.BusId, cell.Slot + direction);
            int targetSlot = GetSlot(targetTerminal);
            EnsureTerminalFree(page, (int)targetTerminal.ID, new HashSet<int>());
            double dx = GetMm(targetTerminal, "PinX") - GetMm(sourceTerminal, "PinX");
            double dy = GetMm(targetTerminal, "PinY") - GetMm(sourceTerminal, "PinY");

            List<int> sourceIds = cell.MemberIds.OrderBy(x => x).ToList();
            SelectIds(page, sourceIds);
            List<double[]> sourcePoints = new List<double[]>();
            List<string> sourceMasters = new List<string>();
            List<string> sourceTexts = new List<string>();
            foreach (int id in sourceIds)
            {
                dynamic sourceShape = page.Shapes.ItemFromID(id);
                sourcePoints.Add(new double[] { GetMm(sourceShape, "PinX"), GetMm(sourceShape, "PinY") });
                sourceMasters.Add(MasterName(sourceShape));
                sourceTexts.Add(SafeText(sourceShape));
            }

            int scope = (int)app.BeginUndoScope(direction > 0 ? "EnergoLogic: Копировать ячейку вправо" : "EnergoLogic: Копировать ячейку влево");
            bool commit = false;
            try
            {
                app.DoCmd(1024);
                dynamic duplicated = app.ActiveWindow.Selection;
                if ((int)duplicated.Count != sourceIds.Count) throw new InvalidOperationException("Visio вернул неполную копию выделения");
                List<int> newIds = SelectionIds(duplicated);
                List<double[]> newPoints = new List<double[]>();
                foreach (int id in newIds)
                {
                    dynamic newShape = page.Shapes.ItemFromID(id);
                    newPoints.Add(new double[] { GetMm(newShape, "PinX"), GetMm(newShape, "PinY") });
                }
                for (int i = 0; i < sourceIds.Count; i++)
                {
                    if (MasterName(page.Shapes.ItemFromID(newIds[i])) != sourceMasters[i] || SafeText(page.Shapes.ItemFromID(newIds[i])) != sourceTexts[i])
                        throw new InvalidOperationException("Visio изменил порядок элементов при копировании; операция отменена");
                }
                double nativeDx = newPoints.Average(p => p[0]) - sourcePoints.Average(p => p[0]);
                double nativeDy = newPoints.Average(p => p[1]) - sourcePoints.Average(p => p[1]);
                duplicated.Move(dx - nativeDx, dy - nativeDy, "mm");

                int anchorIndex = sourceIds.IndexOf(cell.AnchorId);
                if (anchorIndex < 0) throw new InvalidOperationException("Не найден anchor ячейки в копии");
                dynamic newAnchor = page.Shapes.ItemFromID(newIds[anchorIndex]);
                string newCellId = "cell:" + Guid.NewGuid().ToString("N");
                foreach (int id in newIds) SetCellIdentity(page.Shapes.ItemFromID(id), newCellId);
                GlueEndpoint(newAnchor, cell.Endpoint, targetTerminal, cell.ConnectionRow);
                VerifyGlue(newAnchor, cell.Endpoint, (int)targetTerminal.ID, cell.ConnectionRow);
                commit = true;
                return String.Format(CultureInfo.CurrentCulture,
                    "✓ Ячейка скопирована {0}. Место {1} → {2}; сдвиг {3:0.00} мм; Glue восстановлен; identity создана.",
                    direction > 0 ? "вправо" : "влево", cell.Slot, targetSlot, dx);
            }
            finally
            {
                app.EndUndoScope(scope, commit);
            }
        }

        internal string MoveCell(int direction)
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            dynamic sourceTerminal = page.Shapes.ItemFromID(cell.BusTerminalId);
            dynamic targetTerminal = GetBusTerminalBySlot(page, cell.BusId, cell.Slot + direction);
            HashSet<int> own = new HashSet<int>(cell.MemberIds);
            EnsureTerminalFree(page, (int)targetTerminal.ID, own);
            double dx = GetMm(targetTerminal, "PinX") - GetMm(sourceTerminal, "PinX");
            double dy = GetMm(targetTerminal, "PinY") - GetMm(sourceTerminal, "PinY");

            int scope = (int)app.BeginUndoScope(direction > 0 ? "EnergoLogic: Переместить ячейку вправо" : "EnergoLogic: Переместить ячейку влево");
            bool commit = false;
            try
            {
                dynamic anchor = page.Shapes.ItemFromID(cell.AnchorId);
                DetachEndpoint(anchor, cell.Endpoint);
                SelectIds(page, cell.MemberIds);
                app.ActiveWindow.Selection.Move(dx, dy, "mm");
                GlueEndpoint(anchor, cell.Endpoint, targetTerminal, cell.ConnectionRow);
                VerifyGlue(anchor, cell.Endpoint, (int)targetTerminal.ID, cell.ConnectionRow);
                commit = true;
                return String.Format(CultureInfo.CurrentCulture,
                    "✓ Ячейка перемещена {0}. Место {1} → {2}; сдвиг {3:0.00} мм; Glue проверен.",
                    direction > 0 ? "вправо" : "влево", cell.Slot, GetSlot(targetTerminal), dx);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string SelectCell()
        {
            dynamic page = App.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            SelectIds(page, cell.MemberIds);
            return "✓ Выделена вся ячейка: " + cell.MemberIds.Count + " элементов, место шины " + cell.Slot + ".";
        }

        internal string ExactOffset(double dx, double dy)
        {
            if (Math.Abs(dx) < 1e-9 && Math.Abs(dy) < 1e-9) throw new InvalidOperationException("Смещение не может быть нулевым");
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            EnsureNoExternalGlue(page, ids);
            int scope = (int)app.BeginUndoScope("EnergoLogic: Точный сдвиг");
            bool commit = false;
            try
            {
                SelectIds(page, ids);
                app.ActiveWindow.Selection.Move(dx, dy, "mm");
                commit = true;
                return String.Format(CultureInfo.CurrentCulture, "✓ Точный сдвиг: X {0:0.###} мм, Y {1:0.###} мм.", dx, dy);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string BasePointTransform(bool copy, double bx, double by, double tx, double ty)
        {
            double dx = tx - bx;
            double dy = ty - by;
            if (Math.Abs(dx) < 1e-9 && Math.Abs(dy) < 1e-9) throw new InvalidOperationException("Базовая и целевая точки совпадают");
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            EnsureNoExternalGlue(page, ids);
            int scope = (int)app.BeginUndoScope(copy ? "EnergoLogic: Копировать с базовой точкой" : "EnergoLogic: Переместить с базовой точкой");
            bool commit = false;
            try
            {
                SelectIds(page, ids);
                if (copy)
                {
                    List<double[]> src = new List<double[]>();
                    foreach (int id in ids)
                    {
                        dynamic sourceShape = page.Shapes.ItemFromID(id);
                        src.Add(new double[] { GetMm(sourceShape, "PinX"), GetMm(sourceShape, "PinY") });
                    }
                    app.DoCmd(1024);
                    dynamic dup = app.ActiveWindow.Selection;
                    if ((int)dup.Count != ids.Count) throw new InvalidOperationException("Неполная копия выделения");
                    List<int> newIds = SelectionIds(dup);
                    List<double[]> now = new List<double[]>();
                    foreach (int id in newIds)
                    {
                        dynamic duplicateShape = page.Shapes.ItemFromID(id);
                        now.Add(new double[] { GetMm(duplicateShape, "PinX"), GetMm(duplicateShape, "PinY") });
                    }
                    double ndx = now.Average(p => p[0]) - src.Average(p => p[0]);
                    double ndy = now.Average(p => p[1]) - src.Average(p => p[1]);
                    dup.Move(dx - ndx, dy - ndy, "mm");
                    string cellId = "cell:" + Guid.NewGuid().ToString("N");
                    foreach (int id in newIds) if (HasCellIdentity(page.Shapes.ItemFromID(id))) SetCellIdentity(page.Shapes.ItemFromID(id), cellId);
                }
                else app.ActiveWindow.Selection.Move(dx, dy, "mm");
                commit = true;
                return String.Format(CultureInfo.CurrentCulture, "✓ {0} по базовой точке: ΔX {1:0.###} мм, ΔY {2:0.###} мм.", copy ? "Копирование" : "Перемещение", dx, dy);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string Align(string axis)
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count < 2) throw new InvalidOperationException("Для выравнивания выберите минимум два элемента");
            EnsureNoExternalGlue(page, ids);
            dynamic first = page.Shapes.ItemFromID(ids[0]);
            double target = GetMm(first, axis == "x" ? "PinX" : "PinY");
            int scope = (int)app.BeginUndoScope(axis == "x" ? "EnergoLogic: Выровнять по X" : "EnergoLogic: Выровнять по Y");
            bool commit = false;
            try
            {
                foreach (int id in ids)
                {
                    dynamic shape = page.Shapes.ItemFromID(id);
                    SetMm(shape, axis == "x" ? "PinX" : "PinY", target);
                }
                SelectIds(page, ids);
                commit = true;
                return String.Format(CultureInfo.CurrentCulture, "✓ Выровнено {0} элементов по {1} = {2:0.###} мм.", ids.Count, axis.ToUpperInvariant(), target);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string MeasurePitch()
        {
            dynamic page = App.ActivePage;
            List<CellInfo> cells = SelectedCells(page);
            if (cells.Count != 2) throw new InvalidOperationException("Для измерения шага выберите элементы ровно двух ячеек");
            dynamic t1 = page.Shapes.ItemFromID(cells[0].BusTerminalId);
            dynamic t2 = page.Shapes.ItemFromID(cells[1].BusTerminalId);
            if (cells[0].BusId != cells[1].BusId) throw new InvalidOperationException("Ячейки подключены к разным шинам");
            double pitch = Math.Abs(GetMm(t2, "PinX") - GetMm(t1, "PinX"));
            return pitch.ToString("0.###", CultureInfo.InvariantCulture);
        }

        internal string DistributePitch(double pitch)
        {
            if (pitch <= 0) throw new InvalidOperationException("Шаг должен быть больше нуля");
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<CellInfo> cells = SelectedCells(page);
            cells.Sort(delegate(CellInfo left, CellInfo right)
            {
                dynamic leftTerminal = page.Shapes.ItemFromID(left.BusTerminalId);
                dynamic rightTerminal = page.Shapes.ItemFromID(right.BusTerminalId);
                return GetMm(leftTerminal, "PinX").CompareTo(GetMm(rightTerminal, "PinX"));
            });
            if (cells.Count < 2) throw new InvalidOperationException("Для распределения выберите минимум две ячейки");
            int busId = cells[0].BusId;
            if (cells.Any(c => c.BusId != busId)) throw new InvalidOperationException("Все выбранные ячейки должны быть на одной шине");
            int startSlot = cells.Min(c => c.Slot);
            List<Tuple<CellInfo, dynamic>> plan = new List<Tuple<CellInfo, dynamic>>();
            HashSet<int> selectedMembers = new HashSet<int>(cells.SelectMany(c => c.MemberIds));
            for (int i = 0; i < cells.Count; i++)
            {
                dynamic target = GetBusTerminalBySlot(page, busId, startSlot + i);
                if (i > 0)
                {
                    dynamic prev = GetBusTerminalBySlot(page, busId, startSlot + i - 1);
                    double actual = Math.Abs(GetMm(target, "PinX") - GetMm(prev, "PinX"));
                    if (Math.Abs(actual - pitch) > 0.25)
                        throw new InvalidOperationException(String.Format(CultureInfo.CurrentCulture, "Шина имеет шаг {0:0.###} мм, а задан {1:0.###} мм", actual, pitch));
                }
                EnsureTerminalFree(page, (int)target.ID, selectedMembers);
                plan.Add(Tuple.Create(cells[i], target));
            }

            int scope = (int)app.BeginUndoScope("EnergoLogic: Распределить ячейки");
            bool commit = false;
            try
            {
                foreach (Tuple<CellInfo, dynamic> row in plan)
                {
                    CellInfo cell = row.Item1;
                    dynamic target = row.Item2;
                    if ((int)target.ID == cell.BusTerminalId) continue;
                    dynamic sourceTerminal = page.Shapes.ItemFromID(cell.BusTerminalId);
                    double dx = GetMm(target, "PinX") - GetMm(sourceTerminal, "PinX");
                    double dy = GetMm(target, "PinY") - GetMm(sourceTerminal, "PinY");
                    dynamic anchor = page.Shapes.ItemFromID(cell.AnchorId);
                    DetachEndpoint(anchor, cell.Endpoint);
                    SelectIds(page, cell.MemberIds);
                    app.ActiveWindow.Selection.Move(dx, dy, "mm");
                    GlueEndpoint(anchor, cell.Endpoint, target, cell.ConnectionRow);
                }
                SelectIds(page, cells.SelectMany(c => c.MemberIds).Distinct().ToList());
                commit = true;
                return "✓ Ячейки распределены по реальным точкам шины. Шаг: " + pitch.ToString("0.###", CultureInfo.CurrentCulture) + " мм.";
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string RepairGlue(bool previewOnly, bool requireConfirmation)
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count != 1) throw new InvalidOperationException("Для Repair Glue выберите один элемент");
            dynamic shape = page.Shapes.ItemFromID(ids[0]);
            List<ConnectionPointInfo> points = GetAllConnectionPoints(page);
            HashSet<string> connectedEndpoints = BuildConnectedEndpointIndex(page);
            List<Tuple<string, double, double>> endpoints = new List<Tuple<string, double, double>>();
            foreach (string endpoint in new[] { "begin", "end" })
            {
                if (!HasEndpoint(shape, endpoint)) continue;
                if (connectedEndpoints.Contains(EndpointKey((int)shape.ID, endpoint))) continue;
                endpoints.Add(Tuple.Create(endpoint, GetMm(shape, endpoint == "begin" ? "BeginX" : "EndX"), GetMm(shape, endpoint == "begin" ? "BeginY" : "EndY")));
            }
            if (endpoints.Count == 0) throw new InvalidOperationException("У выбранного элемента нет свободного endpoint для ремонта");

            List<Tuple<string, ConnectionPointInfo>> candidates = new List<Tuple<string, ConnectionPointInfo>>();
            foreach (var ep in endpoints)
            {
                foreach (ConnectionPointInfo p in points)
                {
                    if (p.ShapeId == ids[0]) continue;
                    double d = Math.Sqrt(Math.Pow(p.Xmm - ep.Item2, 2) + Math.Pow(p.Ymm - ep.Item3, 2));
                    if (d <= 1.0)
                    {
                        ConnectionPointInfo copy = new ConnectionPointInfo { ShapeId = p.ShapeId, Row = p.Row, Xmm = p.Xmm, Ymm = p.Ymm, DistanceMm = d };
                        candidates.Add(Tuple.Create(ep.Item1, copy));
                    }
                }
            }
            candidates = candidates.OrderBy(c => c.Item2.DistanceMm).ToList();
            if (candidates.Count == 0) throw new InvalidOperationException("Рядом не найдено ни одной реальной connection point (≤ 1 мм)");
            if (candidates.Count > 1 && Math.Abs(candidates[0].Item2.DistanceMm - candidates[1].Item2.DistanceMm) < 0.05)
            {
                string ambiguity = String.Join("; ", candidates.Take(6).Select(c => String.Format(
                    CultureInfo.InvariantCulture,
                    "{0}->shape {1}/Connections.{2}@{3:0.###}mm",
                    c.Item1, c.Item2.ShapeId, c.Item2.Row, c.Item2.DistanceMm)).ToArray());
                throw new InvalidOperationException("Найдено несколько одинаково близких connection point — автоматический ремонт запрещён: " + ambiguity);
            }
            var best = candidates[0];
            string description = String.Format(CultureInfo.CurrentCulture, "{0}: shape {1}, Connections.{2}, расстояние {3:0.###} мм", best.Item1, best.Item2.ShapeId, best.Item2.Row, best.Item2.DistanceMm);
            if (previewOnly) return "Кандидат Repair Glue: " + description;
            if (requireConfirmation)
            {
                DialogResult answer = MessageBox.Show("Найден кандидат:\n\n" + description + "\n\nИсправить Glue?", "EnergoLogic — Repair Glue", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
                if (answer != DialogResult.Yes) return "Repair Glue отменён пользователем.";
            }
            int scope = (int)app.BeginUndoScope("EnergoLogic: Repair Glue");
            bool commit = false;
            try
            {
                GlueEndpoint(shape, best.Item1, page.Shapes.ItemFromID(best.Item2.ShapeId), best.Item2.Row);
                VerifyGlue(shape, best.Item1, best.Item2.ShapeId, best.Item2.Row);
                commit = true;
                return "✓ Glue восстановлен. " + description;
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string Doctor()
        {
            dynamic page = App.ActivePage;
            List<ConnectionPointInfo> points = GetAllConnectionPoints(page);
            HashSet<string> connectedEndpoints = BuildConnectedEndpointIndex(page);
            List<int> bad = new List<int>();
            List<string> messages = new List<string>();
            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic shape = page.Shapes.Item(i);
                int id = (int)shape.ID;
                foreach (string ep in new[] { "begin", "end" })
                {
                    if (!HasEndpoint(shape, ep) || connectedEndpoints.Contains(EndpointKey(id, ep))) continue;
                    double x = GetMm(shape, ep == "begin" ? "BeginX" : "EndX");
                    double y = GetMm(shape, ep == "begin" ? "BeginY" : "EndY");
                    var near = points.Where(p => p.ShapeId != id && Math.Sqrt(Math.Pow(p.Xmm - x, 2) + Math.Pow(p.Ymm - y, 2)) <= 0.8).ToList();
                    if (near.Count > 0)
                    {
                        bad.Add(id);
                        messages.Add("Shape " + id + " " + ep + ": визуально касается connection point, но Glue отсутствует");
                    }
                }
            }
            if (bad.Count > 0) SelectIds(page, bad.Distinct().ToList());
            if (messages.Count == 0) return "✓ Scheme Doctor: явных structural-проблем Glue не найдено.";
            return "⚠ Scheme Doctor: найдено проблем: " + messages.Count + ". Проблемные элементы выделены.\r\n" + String.Join("\r\n", messages.Take(8).ToArray());
        }

        private List<CellInfo> SelectedCells(dynamic page)
        {
            List<int> selection = CurrentTopLevelSelection(page);
            Dictionary<int, CellInfo> unique = new Dictionary<int, CellInfo>();
            foreach (int id in selection)
            {
                CellInfo cell = DiscoverCell(page, id);
                if (!unique.ContainsKey(cell.AnchorId)) unique.Add(cell.AnchorId, cell);
            }
            return unique.Values.ToList();
        }

        private CellInfo DiscoverCellFromSelection(dynamic page)
        {
            List<int> selection = CurrentTopLevelSelection(page);
            Exception last = null;
            foreach (int id in selection)
            {
                try { return DiscoverCell(page, id); }
                catch (Exception ex) { last = ex; }
            }
            string reason = last == null ? "неизвестная причина" : last.Message;
            throw new InvalidOperationException("Не удалось определить ячейку по выделению. Причина: " + reason, last);
        }

        private CellInfo DiscoverCell(dynamic page, int selectedId)
        {
            Dictionary<int, int> childParent = BuildChildParentMap(page);
            HashSet<int> top = TopLevelIds(page);
            Dictionary<int, HashSet<int>> graph = new Dictionary<int, HashSet<int>>();
            foreach (int id in top) graph[id] = new HashSet<int>();
            foreach (int id in top)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, ep);
                    if (target != null && top.Contains(target.TargetId))
                    {
                        graph[id].Add(target.TargetId);
                        graph[target.TargetId].Add(id);
                    }
                }
            }
            if (!top.Contains(selectedId)) throw new InvalidOperationException("Выбранный объект не является top-level элементом схемы");
            HashSet<int> core = new HashSet<int>();
            Stack<int> stack = new Stack<int>();
            stack.Push(selectedId);
            while (stack.Count > 0)
            {
                int cur = stack.Pop();
                if (!core.Add(cur)) continue;
                foreach (int n in graph[cur]) if (!core.Contains(n)) stack.Push(n);
            }

            List<Tuple<int, GlueTarget, int>> anchors = new List<Tuple<int, GlueTarget, int>>();
            foreach (int id in core)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, ep);
                    if (target != null && childParent.ContainsKey(target.TargetId))
                        anchors.Add(Tuple.Create(id, target, childParent[target.TargetId]));
                }
            }
            if (anchors.Count != 1) throw new InvalidOperationException("У ячейки должен быть ровно один внешний Glue к шине; найдено: " + anchors.Count);
            var anchor = anchors[0];
            dynamic terminal = page.Shapes.ItemFromID(anchor.Item2.TargetId);
            int slot = GetSlot(terminal);
            double anchorX = GetMm(page.Shapes.ItemFromID(anchor.Item1), "PinX");
            double minY = Double.PositiveInfinity;
            double maxY = Double.NegativeInfinity;
            foreach (int id in core)
            {
                double y = GetMm(page.Shapes.ItemFromID(id), "PinY");
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            }
            minY -= 10.0;
            maxY += 10.0;
            double pitch = NearestBusPitch(page, anchor.Item3, anchor.Item2.TargetId);
            double half = pitch / 2.0;
            List<int> members = new List<int>(core);
            foreach (int id in top)
            {
                if (id == anchor.Item3) continue;
                dynamic shape = page.Shapes.ItemFromID(id);
                double x = GetMm(shape, "PinX");
                double y = GetMm(shape, "PinY");
                double distance = Math.Abs(x - anchorX);
                if (Math.Abs(distance - half) <= 0.01 && y >= minY && y <= maxY)
                    throw new InvalidOperationException("Неоднозначная граница ячейки: shape " + id + " лежит ровно между соседними ячейками");
                if (distance < half - 0.01 && y >= minY && y <= maxY && !members.Contains(id)) members.Add(id);
            }
            members.Sort();
            return new CellInfo {
                AnchorId = anchor.Item1,
                BusId = anchor.Item3,
                BusTerminalId = anchor.Item2.TargetId,
                Slot = slot,
                ConnectionRow = anchor.Item2.Row,
                Endpoint = anchor.Item2.Endpoint,
                CoreIds = core.OrderBy(x => x).ToList(),
                MemberIds = members
            };
        }

        private double NearestBusPitch(dynamic page, int busId, int sourceTerminalId)
        {
            dynamic bus = page.Shapes.ItemFromID(busId);
            dynamic source = page.Shapes.ItemFromID(sourceTerminalId);
            double sx = GetMm(source, "PinX");
            List<double> distances = new List<double>();
            for (int i = 1; i <= (int)bus.Shapes.Count; i++)
            {
                dynamic child = bus.Shapes.Item(i);
                if ((int)child.ID == sourceTerminalId) continue;
                try { GetSlot(child); }
                catch { continue; }
                double d = Math.Abs(GetMm(child, "PinX") - sx);
                if (d > 0.01) distances.Add(d);
            }
            if (distances.Count == 0) throw new InvalidOperationException("Не удалось определить шаг точек шины");
            return distances.Min();
        }

        private dynamic GetBusTerminalBySlot(dynamic page, int busId, int slot)
        {
            if (slot <= 0) throw new InvalidOperationException("На шине нет места " + slot);
            dynamic bus = page.Shapes.ItemFromID(busId);
            List<dynamic> found = new List<dynamic>();
            for (int i = 1; i <= (int)bus.Shapes.Count; i++)
            {
                dynamic child = bus.Shapes.Item(i);
                try { if (GetSlot(child) == slot) found.Add(child); }
                catch { }
            }
            if (found.Count != 1) throw new InvalidOperationException("Место шины " + slot + " не найдено или неоднозначно");
            return found[0];
        }

        private bool CellExists(dynamic shape, string cellName)
        {
            try
            {
                object raw = shape.CellExistsU(cellName, 0);
                return Convert.ToInt32(raw, CultureInfo.InvariantCulture) != 0;
            }
            catch { return false; }
        }

        private int GetSlot(dynamic terminal)
        {
            try
            {
                if (CellExists(terminal, "User.slot"))
                    return Convert.ToInt32(Math.Round((double)terminal.CellsU("User.slot").ResultIU));
            }
            catch { }
            int slot;
            if (Int32.TryParse(SafeText(terminal).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out slot) && slot > 0) return slot;
            throw new InvalidOperationException("У connection point шины отсутствует номер места");
        }

        private void EnsureTerminalFree(dynamic page, int terminalId, HashSet<int> allowedOwners)
        {
            HashSet<int> top = TopLevelIds(page);
            foreach (int id in top)
            {
                if (allowedOwners.Contains(id)) continue;
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget t = TryGetGlueTarget(shape, ep);
                    if (t != null && t.TargetId == terminalId)
                        throw new InvalidOperationException("Целевое место шины уже занято shape " + id);
                }
            }
        }

        private void EnsureNoExternalGlue(dynamic page, List<int> ids)
        {
            HashSet<int> selected = new HashSet<int>(ids);
            Dictionary<int, int> childParent = BuildChildParentMap(page);
            foreach (int id in ids)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, ep);
                    if (target == null) continue;
                    int owner = childParent.ContainsKey(target.TargetId) ? childParent[target.TargetId] : target.TargetId;
                    if (!selected.Contains(owner))
                        throw new InvalidOperationException("Выделение имеет внешнюю электрическую связь. Используйте предметную команду ячейки, чтобы не порвать Glue.");
                }
            }
        }

        private Dictionary<int, int> BuildChildParentMap(dynamic page)
        {
            Dictionary<int, int> map = new Dictionary<int, int>();
            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic top = page.Shapes.Item(i);
                try
                {
                    for (int j = 1; j <= (int)top.Shapes.Count; j++)
                        map[(int)top.Shapes.Item(j).ID] = (int)top.ID;
                }
                catch { }
            }
            return map;
        }

        private HashSet<int> TopLevelIds(dynamic page)
        {
            HashSet<int> result = new HashSet<int>();
            for (int i = 1; i <= (int)page.Shapes.Count; i++) result.Add((int)page.Shapes.Item(i).ID);
            return result;
        }

        private List<int> CurrentTopLevelSelection(dynamic page)
        {
            dynamic sel = App.ActiveWindow.Selection;
            if (sel == null || (int)sel.Count < 1) throw new InvalidOperationException("Сначала выделите объект(ы) на схеме");
            HashSet<int> top = TopLevelIds(page);
            List<int> ids = new List<int>();
            for (int i = 1; i <= (int)sel.Count; i++)
            {
                dynamic shape = sel.Item(i);
                int id = (int)shape.ID;
                if (!top.Contains(id))
                {
                    try
                    {
                        dynamic parent = shape.ContainingShape;
                        if (parent != null) id = (int)parent.ID;
                    }
                    catch { }
                }
                if (!top.Contains(id)) throw new InvalidOperationException("Выбран дочерний объект, который не удалось нормализовать до top-level shape");
                if (!ids.Contains(id)) ids.Add(id);
            }
            return ids;
        }

        private List<int> SelectionIds(dynamic selection)
        {
            List<int> ids = new List<int>();
            for (int i = 1; i <= (int)selection.Count; i++) ids.Add((int)selection.Item(i).ID);
            return ids;
        }

        private void SelectIds(dynamic page, IEnumerable<int> ids)
        {
            dynamic window = App.ActiveWindow;
            window.DeselectAll();
            foreach (int id in ids) window.Select(page.Shapes.ItemFromID(id), 2);
        }

        private GlueTarget TryGetGlueTarget(dynamic shape, string endpoint)
        {
            if (!HasEndpoint(shape, endpoint)) return null;
            string sourceCellName = endpoint == "begin" ? "BeginX" : "EndX";

            // Primary source of truth: Visio native Connects collection. VTD often
            // serializes internal ShapeSheet references by shape Name rather than
            // Sheet.ID, so parsing FormulaU alone is not topology-safe.
            try
            {
                dynamic connects = shape.Connects;
                for (int index = 1; index <= (int)connects.Count; index++)
                {
                    dynamic connect = connects.Item(index);
                    string fromName;
                    string toName;
                    int targetId;
                    try
                    {
                        fromName = Convert.ToString(connect.FromCell.NameU, CultureInfo.InvariantCulture) ?? "";
                        toName = Convert.ToString(connect.ToCell.NameU, CultureInfo.InvariantCulture) ?? "";
                        targetId = Convert.ToInt32(connect.ToSheet.ID, CultureInfo.InvariantCulture);
                    }
                    catch { continue; }
                    if (!String.Equals(fromName, sourceCellName, StringComparison.OrdinalIgnoreCase)) continue;
                    Match cellMatch = _connectionCellRegex.Match(toName);
                    if (!cellMatch.Success) continue;
                    int row = cellMatch.Groups[1].Success
                        ? Int32.Parse(cellMatch.Groups[1].Value, CultureInfo.InvariantCulture)
                        : Int32.Parse(cellMatch.Groups[2].Value, CultureInfo.InvariantCulture);
                    return new GlueTarget { TargetId = targetId, Row = row, Endpoint = endpoint };
                }
            }
            catch { }

            // Fallback for environments where Connects observation lags immediately
            // after GlueTo. This intentionally supports only explicit Sheet.ID formulas.
            string formula;
            try { formula = Convert.ToString(shape.CellsU(sourceCellName).FormulaU, CultureInfo.InvariantCulture) ?? ""; }
            catch { return null; }
            Match m = _glueRegex.Match(formula);
            if (!m.Success) return null;
            int fallbackRow = m.Groups["rowx"].Success
                ? Int32.Parse(m.Groups["rowx"].Value, CultureInfo.InvariantCulture)
                : Int32.Parse(m.Groups["row"].Value, CultureInfo.InvariantCulture);
            string targetRef = m.Groups["target"].Value.Trim();
            int fallbackTargetId = 0;
            Match sheetMatch = Regex.Match(targetRef, @"^Sheet\.(\d+)$", RegexOptions.IgnoreCase);
            if (sheetMatch.Success)
            {
                fallbackTargetId = Int32.Parse(sheetMatch.Groups[1].Value, CultureInfo.InvariantCulture);
            }
            else
            {
                dynamic page = App.ActivePage;
                List<int> matches = new List<int>();
                for (int index = 1; index <= (int)page.Shapes.Count; index++)
                {
                    dynamic candidate = page.Shapes.Item(index);
                    string name = "";
                    string nameU = "";
                    try { name = Convert.ToString(candidate.Name, CultureInfo.InvariantCulture) ?? ""; } catch { }
                    try { nameU = Convert.ToString(candidate.NameU, CultureInfo.InvariantCulture) ?? ""; } catch { }
                    if (String.Equals(name, targetRef, StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(nameU, targetRef, StringComparison.OrdinalIgnoreCase))
                        matches.Add(Convert.ToInt32(candidate.ID, CultureInfo.InvariantCulture));
                }
                if (matches.Count != 1) return null;
                fallbackTargetId = matches[0];
            }
            return new GlueTarget { TargetId = fallbackTargetId, Row = fallbackRow, Endpoint = endpoint };
        }

        private bool HasEndpoint(dynamic shape, string endpoint)
        {
            return CellExists(shape, endpoint == "begin" ? "BeginX" : "EndX");
        }

        private void DetachEndpoint(dynamic shape, string endpoint)
        {
            string xName = endpoint == "begin" ? "BeginX" : "EndX";
            string yName = endpoint == "begin" ? "BeginY" : "EndY";
            double x = GetMm(shape, xName);
            double y = GetMm(shape, yName);
            SetMm(shape, xName, x);
            SetMm(shape, yName, y);
        }

        private void GlueEndpoint(dynamic shape, string endpoint, dynamic target, int row)
        {
            string sourceName = endpoint == "begin" ? "BeginX" : "EndX";
            string targetName = "Connections.X" + row.ToString(CultureInfo.InvariantCulture);
            if (!CellExists(target, targetName)) throw new InvalidOperationException("У target отсутствует " + targetName);
            shape.CellsU(sourceName).GlueTo(target.CellsU(targetName));
        }

        private void VerifyGlue(dynamic shape, string endpoint, int targetId, int row)
        {
            GlueTarget target = TryGetGlueTarget(shape, endpoint);
            if (target == null || target.TargetId != targetId || target.Row != row)
                throw new InvalidOperationException("Проверка Glue после операции не прошла");
        }

        private string EndpointKey(int shapeId, string endpoint)
        {
            return shapeId.ToString(CultureInfo.InvariantCulture) + ":" + endpoint.ToLowerInvariant();
        }

        private HashSet<string> BuildConnectedEndpointIndex(dynamic page)
        {
            HashSet<string> connected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            Action<dynamic> inspect = null;
            inspect = source =>
            {
                int sourceId;
                try { sourceId = Convert.ToInt32(source.ID, CultureInfo.InvariantCulture); }
                catch { return; }

                foreach (string sourceEndpoint in new[] { "begin", "end" })
                {
                    GlueTarget glue = null;
                    try { glue = TryGetGlueTarget(source, sourceEndpoint); }
                    catch { glue = null; }
                    if (glue == null) continue;

                    connected.Add(EndpointKey(sourceId, sourceEndpoint));
                    try
                    {
                        dynamic target = page.Shapes.ItemFromID(glue.TargetId);
                        string xName = "Connections.X" + glue.Row.ToString(CultureInfo.InvariantCulture);
                        string yName = "Connections.Y" + glue.Row.ToString(CultureInfo.InvariantCulture);
                        if (!CellExists(target, xName) || !CellExists(target, yName)) continue;

                        double localX = (double)target.CellsU(xName).ResultIU;
                        double localY = (double)target.CellsU(yName).ResultIU;
                        double pageX = 0, pageY = 0;
                        target.XYToPage(localX, localY, out pageX, out pageY);
                        double pointX = pageX * 25.4;
                        double pointY = pageY * 25.4;
                        foreach (string targetEndpoint in new[] { "begin", "end" })
                        {
                            if (!HasEndpoint(target, targetEndpoint)) continue;
                            double endpointX = GetMm(target, targetEndpoint == "begin" ? "BeginX" : "EndX");
                            double endpointY = GetMm(target, targetEndpoint == "begin" ? "BeginY" : "EndY");
                            double dx = pointX - endpointX;
                            double dy = pointY - endpointY;
                            if (Math.Sqrt(dx * dx + dy * dy) <= 0.02)
                                connected.Add(EndpointKey(glue.TargetId, targetEndpoint));
                        }
                    }
                    catch { }
                }

                try
                {
                    for (int child = 1; child <= (int)source.Shapes.Count; child++)
                        inspect(source.Shapes.Item(child));
                }
                catch { }
            };

            for (int index = 1; index <= (int)page.Shapes.Count; index++)
                inspect(page.Shapes.Item(index));
            return connected;
        }

        private List<ConnectionPointInfo> GetAllConnectionPoints(dynamic page)
        {
            List<ConnectionPointInfo> result = new List<ConnectionPointInfo>();
            Action<dynamic> addShape = null;
            addShape = shape =>
            {
                int sid = (int)shape.ID;
                for (int row = 1; row <= 32; row++)
                {
                    string xName = "Connections.X" + row.ToString(CultureInfo.InvariantCulture);
                    string yName = "Connections.Y" + row.ToString(CultureInfo.InvariantCulture);
                    try
                    {
                        if (!CellExists(shape, xName)) continue;
                        double x = (double)shape.CellsU(xName).ResultIU;
                        double y = (double)shape.CellsU(yName).ResultIU;
                        double px = 0, py = 0;
                        shape.XYToPage(x, y, out px, out py);
                        result.Add(new ConnectionPointInfo { ShapeId = sid, Row = row, Xmm = px * 25.4, Ymm = py * 25.4 });
                    }
                    catch { }
                }
                try { for (int i = 1; i <= (int)shape.Shapes.Count; i++) addShape(shape.Shapes.Item(i)); }
                catch { }
            };
            for (int i = 1; i <= (int)page.Shapes.Count; i++) addShape(page.Shapes.Item(i));
            return result;
        }

        private double GetMm(dynamic shape, string cell) { return (double)shape.CellsU(cell).ResultIU * 25.4; }
        private void SetMm(dynamic shape, string cell, double value) { shape.CellsU(cell).FormulaU = value.ToString("0.############", CultureInfo.InvariantCulture) + " mm"; }
        private string SafeText(dynamic shape) { try { return (string)shape.Text ?? ""; } catch { return ""; } }
        private string MasterName(dynamic shape) { try { dynamic m = shape.Master; return m == null ? "" : (string)m.NameU; } catch { return ""; } }

        private bool HasCellIdentity(dynamic shape)
        {
            return CellExists(shape, "User.EnergoLogicCellId");
        }

        private void SetCellIdentity(dynamic shape, string cellId)
        {
            const short visSectionUser = 242;
            object sectionExistsRaw = shape.SectionExists(visSectionUser, 0);
            if (Convert.ToInt32(sectionExistsRaw, CultureInfo.InvariantCulture) == 0) shape.AddSection(visSectionUser);
            if (!CellExists(shape, "User.EnergoLogicCellId")) shape.AddNamedRow(visSectionUser, "EnergoLogicCellId", 0);
            shape.CellsU("User.EnergoLogicCellId").FormulaU = "\"" + cellId + "\"";
        }
    }

    internal sealed class EditorForm : Form
    {
        private readonly Connect _addin;
        private readonly TextBox _status;
        private readonly NumericUpDown _dx;
        private readonly NumericUpDown _dy;
        private readonly NumericUpDown _bx;
        private readonly NumericUpDown _by;
        private readonly NumericUpDown _tx;
        private readonly NumericUpDown _ty;
        private readonly NumericUpDown _pitch;

        public EditorForm(Connect addin)
        {
            _addin = addin;
            Text = "EnergoLogic — инструменты Visio";
            Width = 420;
            Height = 690;
            MinimumSize = new Size(380, 600);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.SizableToolWindow;
            ShowInTaskbar = false;
            Font = new Font("Segoe UI", 9F);
            TopMost = false;

            TabControl tabs = new TabControl { Dock = DockStyle.Top, Height = 490 };
            TabPage cellTab = new TabPage("Ячейки");
            TabPage geoTab = new TabPage("Геометрия");
            TabPage checkTab = new TabPage("Проверка");
            tabs.TabPages.Add(cellTab); tabs.TabPages.Add(geoTab); tabs.TabPages.Add(checkTab);

            TableLayoutPanel cells = Panel2();
            cells.Controls.Add(Button("Копировать ←", (s,e)=>Run(()=>_addin.DuplicateCell(-1))),0,0);
            cells.Controls.Add(Button("Копировать →", (s,e)=>Run(()=>_addin.DuplicateCell(1))),1,0);
            cells.Controls.Add(Button("Переместить ←", (s,e)=>Run(()=>_addin.MoveCell(-1))),0,1);
            cells.Controls.Add(Button("Переместить →", (s,e)=>Run(()=>_addin.MoveCell(1))),1,1);
            cells.Controls.Add(Button("Выделить всю ячейку", (s,e)=>Run(()=>_addin.SelectCell())),0,2);
            cells.SetColumnSpan(cells.GetControlFromPosition(0,2),2);
            cellTab.Controls.Add(cells);

            FlowLayoutPanel gluePanel = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 120, FlowDirection = FlowDirection.TopDown, Padding = new Padding(10) };
            gluePanel.Controls.Add(ButtonWide("Найти проблему Glue", (s,e)=>Run(()=>_addin.RepairGlue(true, false))));
            gluePanel.Controls.Add(ButtonWide("Repair Glue…", (s,e)=>Run(()=>_addin.RepairGlue(false, true))));
            cellTab.Controls.Add(gluePanel);

            TableLayoutPanel geo = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4, RowCount = 9, Padding = new Padding(10) };
            for(int i=0;i<4;i++) geo.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,25));
            _dx = Num(-500,500,0); _dy = Num(-500,500,0);
            geo.Controls.Add(new Label{Text="ΔX, мм",AutoSize=true},0,0); geo.Controls.Add(_dx,1,0);
            geo.Controls.Add(new Label{Text="ΔY, мм",AutoSize=true},2,0); geo.Controls.Add(_dy,3,0);
            Button offset = ButtonWide("Применить точный сдвиг", (s,e)=>Run(()=>_addin.ExactOffset((double)_dx.Value,(double)_dy.Value)));
            geo.Controls.Add(offset,0,1); geo.SetColumnSpan(offset,4);
            Button ax=Button("Выровнять X",(s,e)=>Run(()=>_addin.Align("x"))); Button ay=Button("Выровнять Y",(s,e)=>Run(()=>_addin.Align("y")));
            geo.Controls.Add(ax,0,2); geo.SetColumnSpan(ax,2); geo.Controls.Add(ay,2,2); geo.SetColumnSpan(ay,2);

            _bx=Num(-2000,2000,0); _by=Num(-2000,2000,0); _tx=Num(-2000,2000,0); _ty=Num(-2000,2000,0);
            geo.Controls.Add(new Label{Text="База X",AutoSize=true},0,3); geo.Controls.Add(_bx,1,3); geo.Controls.Add(new Label{Text="База Y",AutoSize=true},2,3); geo.Controls.Add(_by,3,3);
            geo.Controls.Add(new Label{Text="Цель X",AutoSize=true},0,4); geo.Controls.Add(_tx,1,4); geo.Controls.Add(new Label{Text="Цель Y",AutoSize=true},2,4); geo.Controls.Add(_ty,3,4);
            Button bc=Button("Копировать по базе",(s,e)=>Run(()=>_addin.BasePointTransform(true,(double)_bx.Value,(double)_by.Value,(double)_tx.Value,(double)_ty.Value)));
            Button bm=Button("Переместить по базе",(s,e)=>Run(()=>_addin.BasePointTransform(false,(double)_bx.Value,(double)_by.Value,(double)_tx.Value,(double)_ty.Value)));
            geo.Controls.Add(bc,0,5); geo.SetColumnSpan(bc,2); geo.Controls.Add(bm,2,5); geo.SetColumnSpan(bm,2);

            _pitch=Num(1,500,40); geo.Controls.Add(new Label{Text="Шаг ячеек, мм",AutoSize=true},0,6); geo.Controls.Add(_pitch,1,6);
            Button measure=Button("Измерить шаг",(s,e)=>RunPitchMeasure()); Button dist=Button("Распределить",(s,e)=>Run(()=>_addin.DistributePitch((double)_pitch.Value)));
            geo.Controls.Add(measure,2,6); geo.Controls.Add(dist,3,6);
            geoTab.Controls.Add(geo);

            FlowLayoutPanel checks = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, Padding = new Padding(14), WrapContents=false };
            checks.Controls.Add(ButtonWide("Проверить схему", (s,e)=>Run(()=>_addin.Doctor())));
            checks.Controls.Add(new Label { AutoSize=true, MaximumSize=new Size(350,0), Text="Scheme Doctor ищет опасные случаи: визуальное касание без реального Glue и выделяет проблемные элементы." });
            checkTab.Controls.Add(checks);

            _status = new TextBox { Dock=DockStyle.Fill, Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Vertical, BackColor=SystemColors.Window, Text="EnergoLogic готов. Выберите объект на схеме и используйте команду выше." };
            _status.Name = "EnergoLogicStatus";
            _status.AccessibleName = "EnergoLogic status";
            Panel statusPanel = new Panel { Dock=DockStyle.Fill, Padding=new Padding(8) };
            statusPanel.Controls.Add(_status);

            Controls.Add(statusPanel);
            Controls.Add(tabs);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing) { e.Cancel=true; Hide(); return; }
            base.OnFormClosing(e);
        }

        private void Run(Func<string> action)
        {
            try { _status.Text = action(); }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void RunPitchMeasure()
        {
            try
            {
                string value = _addin.MeasurePitch();
                decimal parsed;
                if (Decimal.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed)) _pitch.Value = Math.Min(_pitch.Maximum, Math.Max(_pitch.Minimum, parsed));
                _status.Text = "✓ Измеренный шаг: " + value + " мм.";
            }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private string Friendly(Exception ex)
        {
            Exception cur=ex; while(cur.InnerException!=null) cur=cur.InnerException;
            return cur.Message;
        }

        private TableLayoutPanel Panel2()
        {
            TableLayoutPanel p=new TableLayoutPanel{Dock=DockStyle.Top,Height=180,ColumnCount=2,RowCount=3,Padding=new Padding(10)};
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50)); p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            return p;
        }
        private Button Button(string text, EventHandler h) { Button b=new Button{Text=text,Dock=DockStyle.Fill,Height=38,Margin=new Padding(5),AccessibleName=text}; b.Click+=h; return b; }
        private Button ButtonWide(string text, EventHandler h) { Button b=new Button{Text=text,Width=330,Height=38,Margin=new Padding(4),AccessibleName=text}; b.Click+=h; return b; }
        private NumericUpDown Num(decimal min, decimal max, decimal value) { return new NumericUpDown{Minimum=min,Maximum=max,Value=value,DecimalPlaces=2,Increment=0.5M,Dock=DockStyle.Fill}; }
    }
}
