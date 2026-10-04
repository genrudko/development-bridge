using System;
using System.Collections.Generic;
using System.Drawing;
using System.Diagnostics;
using System.IO;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio Editor")]
[assembly: AssemblyVersion("0.3.35.0")]

namespace EnergoLogicVisioEditor
{
    internal sealed class GlueTarget
    {
        public int TargetId;
        public int Row;
        public string Endpoint;
    }

    internal sealed class GlueEdgeInfo
    {
        public int SourceId;
        public string Endpoint;
        public int TargetId;
        public int Row;
    }

    internal sealed class CellMoveState
    {
        public CellInfo Cell;
        public int TargetTerminalId;
        public double Dx;
        public double Dy;
        public List<GlueEdgeInfo> InternalGlue = new List<GlueEdgeInfo>();
    }

    internal sealed class ReplacementCompletionState
    {
        public int ReplacementId;
        public string CellId = "";
        public double Xmm;
        public double Ymm;
        public int ExpectedMemberCount;
        public List<int> ExpectedMemberIds = new List<int>();
        public List<GlueEdgeInfo> ExpectedGlue = new List<GlueEdgeInfo>();
        public string SuccessPrefix = "";
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
    [Guid("C4AC16D4-DB4F-416B-BB13-1D84E22B781C")]
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
        string ApiVisualDiagnostics();
        string ApiBusDiagnostics();
        string ApiExtendBusRight();
        string ApiTrimBusRight();
        string ApiReconnectBegin();
        string ApiReconnectEnd();
        string ApiShowPanel();
        string ApiExactOffset(double dxMm, double dyMm);
        string ApiAlignX();
        string ApiAlignY();
        string ApiBaseCopy(double bx, double by, double tx, double ty);
        string ApiBaseMove(double bx, double by, double tx, double ty);
        string ApiMeasurePitch();
        string ApiDistributePitch(double pitchMm);
        string ApiCoordinates();
        string ApiNudgeLeft();
        string ApiNudgeRight();
        string ApiNudgeUp();
        string ApiNudgeDown();
        string ApiRenumberCell(string newDesignation);
        string ApiBindCellIdentity();
        string ApiCaptureReplacementSample();
        string ApiReplaceEquipmentFromSample();
        string ApiInsertEquipmentIntoConnectionFromSample();
        string ApiOperationStatus();
        string ApiCompletePendingTopology();
        string ApiVersion();
    }

    [ComVisible(true)]
    [Guid("6F661F76-44D3-4CC8-8B2B-E64E8F8BF335")]
    [ProgId("EnergoLogic.VisioEditorAddinV335")]
    [ClassInterface(ClassInterfaceType.AutoDual)]
    public sealed class Connect : IDTExtensibility2, IEnergoLogicEditorApi
    {
        private object _application;
        private object _addInInstance;
        private EditorForm _form;
        private CommandBar _bar;
        private CommandBarButton _toggleButton;
        private _CommandBarButtonEvents_ClickEventHandler _toggleHandler;
        private readonly object _asyncSync = new object();
        private bool _asyncPending = false;
        private string _asyncToken = "";
        private string _asyncState = "idle";
        private string _asyncMessage = "EnergoLogic готов.";
        private string _pendingDocumentName = "";
        private string _pendingPageNameU = "";
        private List<CellMoveState> _pendingStates = null;
        private List<int> _pendingFinalSelection = null;
        private string _pendingSuccessPrefix = "";
        private ReplacementCompletionState _pendingReplacement = null;
        private object _replacementMaster = null;
        private string _replacementMasterName = "";
        private string _replacementInsertSourceEndpoint = "";
        private int _replacementInsertReceiveRow = 0;
        private Process _pendingTopologyHelperProcess = null;
        private string _pendingTopologyPlanPath = "";
        private string _pendingTopologyResultPath = "";
        private int _pendingTopologyCycles = 0;
        private int _pendingStablePasses = 0;
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
            try
            {
                if (_toggleButton != null && _toggleHandler != null)
                    _toggleButton.Click -= _toggleHandler;
            }
            catch { }
            try { if (_form != null && !_form.IsDisposed) _form.Dispose(); } catch { }
            try { if (_bar != null) _bar.Delete(); } catch { }
            _form = null;
            _toggleHandler = null;
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
        public string ApiVisualDiagnostics() { return VisualDiagnostics(); }
        public string ApiBusDiagnostics() { return BusDiagnostics(); }
        public string ApiExtendBusRight() { return ExtendBusRight(); }
        public string ApiTrimBusRight() { return TrimBusRight(); }
        public string ApiReconnectBegin() { return ReconnectEndpoint("begin"); }
        public string ApiReconnectEnd() { return ReconnectEndpoint("end"); }
        public string ApiShowPanel() { ShowPanel(); return "✓ Панель EnergoLogic показана."; }
        public string ApiExactOffset(double dxMm, double dyMm) { return ExactOffset(dxMm, dyMm); }
        public string ApiAlignX() { return Align("x"); }
        public string ApiAlignY() { return Align("y"); }
        public string ApiBaseCopy(double bx, double by, double tx, double ty) { return BasePointTransform(true, bx, by, tx, ty); }
        public string ApiBaseMove(double bx, double by, double tx, double ty) { return BasePointTransform(false, bx, by, tx, ty); }
        public string ApiMeasurePitch() { return MeasurePitch(); }
        public string ApiDistributePitch(double pitchMm) { return DistributePitch(pitchMm); }
        public string ApiCoordinates() { return Coordinates(); }
        public string ApiNudgeLeft() { return ExactOffset(-1.0, 0.0); }
        public string ApiNudgeRight() { return ExactOffset(1.0, 0.0); }
        public string ApiNudgeUp() { return ExactOffset(0.0, 1.0); }
        public string ApiNudgeDown() { return ExactOffset(0.0, -1.0); }
        public string ApiRenumberCell(string newDesignation) { return RenumberCell(newDesignation); }
        public string ApiBindCellIdentity() { return BindCellIdentity(); }
        public string ApiCaptureReplacementSample() { return CaptureReplacementSample(); }
        public string ApiReplaceEquipmentFromSample() { return ReplaceEquipmentFromSample(); }
        public string ApiInsertEquipmentIntoConnectionFromSample() { return InsertEquipmentIntoConnectionFromSample(); }
        public string ApiOperationStatus()
        {
            lock (_asyncSync)
                return "state=" + _asyncState + "; token=" + _asyncToken + "; message=" + _asyncMessage;
        }
        public string ApiCompletePendingTopology() { return CompletePendingTopology(); }
        public string ApiVersion() { return "0.3.35"; }

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
            List<GlueEdgeInfo> sourceInternalGlue = CaptureInternalGlue(page, sourceIds);
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
                SettleVisioAfterGeometryChange();

                int anchorIndex = sourceIds.IndexOf(cell.AnchorId);
                if (anchorIndex < 0) throw new InvalidOperationException("Не найден anchor ячейки в копии");
                dynamic newAnchor = page.Shapes.ItemFromID(newIds[anchorIndex]);
                string newCellId = "cell:" + Guid.NewGuid().ToString("N");
                foreach (int id in newIds) SetCellIdentity(page.Shapes.ItemFromID(id), newCellId);
                GlueEndpoint(newAnchor, cell.Endpoint, targetTerminal, cell.ConnectionRow);
                VerifyGlue(newAnchor, cell.Endpoint, (int)targetTerminal.ID, cell.ConnectionRow);
                List<GlueEdgeInfo> duplicateInternalGlue = CaptureInternalGlue(page, newIds);
                if (duplicateInternalGlue.Count != sourceInternalGlue.Count)
                    throw new InvalidOperationException(
                        "Visio потерял внутренние Glue при копировании ячейки; операция отменена"
                    );
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
            CellMoveState state = new CellMoveState {
                Cell = cell,
                TargetTerminalId = (int)targetTerminal.ID,
                Dx = dx,
                Dy = dy,
                InternalGlue = CaptureInternalGlue(page, cell.MemberIds)
            };

            int scope = (int)app.BeginUndoScope(direction > 0 ? "EnergoLogic: Переместить ячейку вправо" : "EnergoLogic: Переместить ячейку влево");
            bool geometryCommit = false;
            try
            {
                dynamic anchor = page.Shapes.ItemFromID(cell.AnchorId);
                DetachEndpoint(anchor, cell.Endpoint);
                SelectIds(page, cell.MemberIds);
                app.ActiveWindow.Selection.Move(dx, dy, "mm");
                geometryCommit = true;
            }
            finally
            {
                app.EndUndoScope(scope, geometryCommit);
            }

            if (!geometryCommit)
                throw new InvalidOperationException("Перемещение ячейки не было завершено");

            SettleVisioAfterGeometryChange();
            try
            {
                int restoredInternal = RestoreCellTopologyAfterMove(page, state);
                SelectIds(page, cell.MemberIds);
                return String.Format(CultureInfo.CurrentCulture,
                    "✓ Ячейка перемещена {0}. Место {1} → {2}; сдвиг {3:0.00} мм; внутренние Glue проверены, восстановлено: {4}.",
                    direction > 0 ? "вправо" : "влево", cell.Slot, GetSlot(targetTerminal), dx, restoredInternal);
            }
            catch (Exception topologyError)
            {
                string compensation = CompensateCellMoves(page, new List<CellMoveState> { state });
                throw new InvalidOperationException(
                    "Перемещение отменено: не удалось восстановить электрические связи после геометрического сдвига. " +
                    compensation + " Причина: " + topologyError.Message,
                    topologyError
                );
            }
        }

        internal string SelectCell()
        {
            dynamic page = App.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            SelectIds(page, cell.MemberIds);
            return "✓ Выделена вся ячейка: " + cell.MemberIds.Count + " элементов, место шины " + cell.Slot + ".";
        }

        internal string BindCellIdentity()
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            HashSet<string> existing = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (int id in cell.MemberIds)
            {
                string identity = GetCellIdentity(page.Shapes.ItemFromID(id));
                if (!String.IsNullOrWhiteSpace(identity)) existing.Add(identity);
            }
            if (existing.Count > 1)
                throw new InvalidOperationException(
                    "В составе ячейки найдены конфликтующие EnergoLogicCellId: " +
                    String.Join(", ", existing.OrderBy(x => x).ToArray())
                );

            string cellId = existing.Count == 1
                ? existing.First()
                : "cell:" + Guid.NewGuid().ToString("N");

            bool alreadyComplete = true;
            foreach (int id in cell.MemberIds)
            {
                if (!String.Equals(
                        GetCellIdentity(page.Shapes.ItemFromID(id)),
                        cellId,
                        StringComparison.OrdinalIgnoreCase))
                {
                    alreadyComplete = false;
                    break;
                }
            }

            int scope = (int)app.BeginUndoScope("EnergoLogic: Закрепить состав ячейки");
            bool commit = false;
            try
            {
                foreach (int id in cell.MemberIds)
                    SetCellIdentity(page.Shapes.ItemFromID(id), cellId);

                foreach (int id in cell.MemberIds)
                {
                    string actual = GetCellIdentity(page.Shapes.ItemFromID(id));
                    if (!String.Equals(actual, cellId, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException(
                            "Не удалось подтвердить EnergoLogicCellId у shape " + id
                        );
                }

                SelectIds(page, cell.MemberIds);
                commit = true;
                return String.Format(
                    CultureInfo.CurrentCulture,
                    alreadyComplete
                        ? "✓ Состав ячейки уже закреплён: {0} элементов; identity {1}."
                        : "✓ Состав ячейки закреплён: {0} элементов; identity {1}.",
                    cell.MemberIds.Count,
                    cellId
                );
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string CaptureReplacementSample()
        {
            dynamic page = App.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count != 1)
                throw new InvalidOperationException("Для образца замены выберите ровно один элемент");

            dynamic shape = page.Shapes.ItemFromID(ids[0]);
            dynamic master = null;
            try { master = shape.Master; } catch { }
            if (master == null)
                throw new InvalidOperationException("У выбранного элемента нет master — использовать его как образец нельзя");

            string name = MasterName(shape);
            if (String.IsNullOrWhiteSpace(name))
            {
                try { name = Convert.ToString(master.Name, CultureInfo.CurrentCulture) ?? ""; } catch { }
            }
            if (String.IsNullOrWhiteSpace(name))
                throw new InvalidOperationException("Не удалось определить имя master у образца");

            _replacementMaster = master;
            _replacementMasterName = name;
            _replacementInsertSourceEndpoint = "";
            _replacementInsertReceiveRow = 0;

            try
            {
                GlueTarget begin = TryGetGlueTarget(shape, "begin");
                GlueTarget end = TryGetGlueTarget(shape, "end");
                if ((begin == null) != (end == null))
                {
                    _replacementInsertSourceEndpoint = begin != null ? "begin" : "end";
                    string receiveEndpoint = _replacementInsertSourceEndpoint == "begin" ? "end" : "begin";
                    _replacementInsertReceiveRow = FindConnectionPointRowAtEndpoint(
                        shape,
                        receiveEndpoint,
                        0.10
                    );
                }
            }
            catch
            {
                _replacementInsertSourceEndpoint = "";
                _replacementInsertReceiveRow = 0;
            }

            string insertProfile =
                !String.IsNullOrWhiteSpace(_replacementInsertSourceEndpoint) &&
                _replacementInsertReceiveRow > 0
                ? String.Format(
                    CultureInfo.CurrentCulture,
                    " Профиль вставки: {0} → Connections.{1}.",
                    _replacementInsertSourceEndpoint,
                    _replacementInsertReceiveRow
                )
                : " Профиль вставки не определён; образец доступен только для замены.";
            return "✓ Образец замены запомнен: " + name + "." + insertProfile;
        }

        internal string ReplaceEquipmentFromSample()
        {
            if (_replacementMaster == null)
                throw new InvalidOperationException("Сначала выберите элемент-образец и нажмите «Запомнить образец»");

            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count != 1)
                throw new InvalidOperationException("Для замены выберите ровно один элемент");

            int oldId = ids[0];
            dynamic target = page.Shapes.ItemFromID(oldId);
            string cellId = GetCellIdentity(target);
            if (String.IsNullOrWhiteSpace(cellId))
                throw new InvalidOperationException(
                    "Перед заменой закрепите состав ячейки, чтобы EnergoLogic мог проверить topology после операции"
                );

            CellInfo cell = DiscoverCell(page, oldId);
            EnsureReplaceTargetSafe(page, cell, oldId);

            string oldMasterName = MasterName(target);
            string oldText = SafeText(target);
            double oldX = GetMm(target, "PinX");
            double oldY = GetMm(target, "PinY");
            bool hasEndpointGeometry =
                HasEndpoint(target, "begin") &&
                HasEndpoint(target, "end");
            double oldBeginX = 0.0;
            double oldBeginY = 0.0;
            double oldEndX = 0.0;
            double oldEndY = 0.0;
            if (hasEndpointGeometry)
            {
                oldBeginX = GetMm(target, "BeginX");
                oldBeginY = GetMm(target, "BeginY");
                oldEndX = GetMm(target, "EndX");
                oldEndY = GetMm(target, "EndY");
            }

            double oldAngle = 0.0;
            bool hasAngle = CellExists(target, "Angle");
            if (hasAngle)
            {
                try { oldAngle = Convert.ToDouble(target.CellsU("Angle").ResultIU, CultureInfo.InvariantCulture); }
                catch { hasAngle = false; }
            }
            double oldWidth = 0.0;
            bool hasWidth = CellExists(target, "Width");
            if (hasWidth)
            {
                try { oldWidth = GetMm(target, "Width"); }
                catch { hasWidth = false; }
            }

            List<GlueEdgeInfo> internalGlue = CaptureInternalGlue(page, cell.MemberIds);
            bool targetWasAnchor = oldId == cell.AnchorId;

            int scope = (int)app.BeginUndoScope("EnergoLogic: Заменить оборудование по образцу");
            bool commit = false;
            try
            {
                dynamic replacement;
                string backend;
                // Native Shape.ReplaceShape is deliberately NOT the default even on
                // Visio 2013+. On this VTD-managed electrical drawing it schedules a
                // delayed dependency rewrite that corrupts an unrelated internal
                // endpoint (244.End) after every apparently clean topology check.
                // The drop/rewire transaction is also the required Visio 2010 path,
                // so one deterministic backend is preferable across all supported
                // Visio versions. Keep the native code behind an explicit future gate.
                bool useNativeReplaceShape = false;
                if (useNativeReplaceShape && SupportsNativeReplaceShape())
                {
                    replacement = target.ReplaceShape(_replacementMaster, 1);
                    backend = "native ReplaceShape";
                }
                else
                {
                    if (targetWasAnchor)
                        DetachEndpoint(target, cell.Endpoint);
                    replacement = page.Drop(_replacementMaster, oldX / 25.4, oldY / 25.4);
                    backend = "drop/rewire compatibility";
                }
                if (replacement == null)
                    throw new InvalidOperationException("Visio не вернул replacement shape");

                int newId = Convert.ToInt32(replacement.ID, CultureInfo.InvariantCulture);
                try { replacement.Text = oldText; } catch { }
                SetCellIdentity(replacement, cellId);

                // For 1-D electrical apparatus the engineering geometry is the
                // endpoint pair, not merely PinX/PinY. A dropped master may carry a
                // different default length even when its sample instance is identical.
                // Materialize the target's exact endpoint coordinates before topology
                // restoration so Begin/End, length, angle and centre are preserved.
                if (hasEndpointGeometry &&
                    HasEndpoint(replacement, "begin") &&
                    HasEndpoint(replacement, "end"))
                {
                    SetMm(replacement, "BeginX", oldBeginX);
                    SetMm(replacement, "BeginY", oldBeginY);
                    SetMm(replacement, "EndX", oldEndX);
                    SetMm(replacement, "EndY", oldEndY);
                }
                else if (hasAngle && CellExists(replacement, "Angle"))
                {
                    replacement.CellsU("Angle").FormulaU =
                        oldAngle.ToString("0.############", CultureInfo.InvariantCulture) + " rad";
                }

                // The VTD bus-terminal shape (for example Sheet.106) cannot be
                // targeted reliably by GlueTo from an out-of-process COM client:
                // Visio returns "Недопустимый код листа". Bind the replacement
                // anchor while still inside the add-in callback, where the same
                // Glue path is proven by Duplicate Cell. The external helper then
                // verifies/stabilizes the complete topology but must not need to
                // create this bus Glue from scratch.
                if (targetWasAnchor)
                {
                    dynamic busTerminal = page.Shapes.ItemFromID(cell.BusTerminalId);
                    GlueEndpoint(
                        replacement,
                        cell.Endpoint,
                        busTerminal,
                        cell.ConnectionRow
                    );
                    VerifyGlue(
                        replacement,
                        cell.Endpoint,
                        cell.BusTerminalId,
                        cell.ConnectionRow
                    );
                }

                if (!useNativeReplaceShape)
                {
                    try { target.Delete(); }
                    catch (Exception ex)
                    {
                        throw new InvalidOperationException("Не удалось удалить исходный shape после drop/rewire replacement", ex);
                    }
                }

                if (Math.Abs(GetMm(replacement, "PinX") - oldX) > 0.1 ||
                    Math.Abs(GetMm(replacement, "PinY") - oldY) > 0.1)
                    throw new InvalidOperationException("После замены изменился engineering anchor оборудования");
                if (hasWidth && CellExists(replacement, "Width") &&
                    Math.Abs(GetMm(replacement, "Width") - oldWidth) > 0.1)
                    throw new InvalidOperationException("После замены изменилась engineering length оборудования");
                if (!String.Equals(GetCellIdentity(replacement), cellId, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("После замены потеряна identity ячейки");

                List<GlueEdgeInfo> expected = BuildReplacementExpectedGlue(
                    cell, internalGlue, oldId, newId
                );
                List<int> expectedMembers = cell.MemberIds
                    .Select(id => id == oldId ? newId : id)
                    .Distinct()
                    .OrderBy(id => id)
                    .ToList();

                ReplacementCompletionState pending = new ReplacementCompletionState {
                    ReplacementId = newId,
                    CellId = cellId,
                    Xmm = oldX,
                    Ymm = oldY,
                    ExpectedMemberCount = cell.MemberIds.Count,
                    ExpectedMemberIds = expectedMembers,
                    ExpectedGlue = expected,
                    SuccessPrefix = String.Format(
                        CultureInfo.CurrentCulture,
                        "✓ Оборудование заменено: {0} → {1}. Backend: {2}",
                        String.IsNullOrWhiteSpace(oldMasterName) ? ("shape " + oldId) : oldMasterName,
                        _replacementMasterName,
                        backend
                    )
                };

                SelectIds(page, new[] { newId });
                commit = true;
                return ScheduleStableTopologyCompletion(page, pending);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string InsertEquipmentIntoConnectionFromSample()
        {
            if (_replacementMaster == null)
                throw new InvalidOperationException("Сначала выберите элемент-образец и нажмите «Запомнить образец»");
            if (String.IsNullOrWhiteSpace(_replacementInsertSourceEndpoint) ||
                _replacementInsertReceiveRow <= 0)
                throw new InvalidOperationException(
                    "У образца не удалось определить безопасный VTD port profile для вставки. " +
                    "Для этого master доступна только замена оборудования."
                );

            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count != 1)
                throw new InvalidOperationException("Для вставки выберите ровно одну 1-D связь");

            int connectionId = ids[0];
            dynamic connection = page.Shapes.ItemFromID(connectionId);
            if (!HasEndpoint(connection, "begin") || !HasEndpoint(connection, "end"))
                throw new InvalidOperationException("Выбранный объект не является 1-D связью с Begin/End");

            string cellId = GetCellIdentity(connection);
            if (String.IsNullOrWhiteSpace(cellId))
                throw new InvalidOperationException("Перед вставкой закрепите состав ячейки");

            CellInfo cell = DiscoverCell(page, connectionId);
            if (connectionId == cell.AnchorId)
                throw new InvalidOperationException(
                    "Нельзя разрезать bus-anchor ячейки; выберите внутреннюю 1-D связь"
                );

            GlueTarget beginTarget = TryGetGlueTarget(connection, "begin");
            GlueTarget endTarget = TryGetGlueTarget(connection, "end");
            if (beginTarget == null || endTarget == null)
                throw new InvalidOperationException(
                    "Для вставки выбранная связь должна иметь Glue на обоих концах"
                );

            List<GlueEdgeInfo> internalGlue = CaptureInternalGlue(page, cell.MemberIds);
            if (internalGlue.Any(edge => edge.TargetId == connectionId))
                throw new InvalidOperationException(
                    "К выбранной связи подключены другие элементы; автоматический разрез неоднозначен"
                );

            double beginX = GetMm(connection, "BeginX");
            double beginY = GetMm(connection, "BeginY");
            double endX = GetMm(connection, "EndX");
            double endY = GetMm(connection, "EndY");
            double dx = endX - beginX;
            double dy = endY - beginY;
            double connectionLength = Math.Sqrt(dx * dx + dy * dy);
            if (connectionLength < 2.0)
                throw new InvalidOperationException("Выбранная связь слишком короткая для вставки");

            double ux = dx / connectionLength;
            double uy = dy / connectionLength;
            double centerX = (beginX + endX) / 2.0;
            double centerY = (beginY + endY) / 2.0;

            int scope = (int)app.BeginUndoScope("EnergoLogic: Вставить оборудование в связь");
            bool commit = false;
            try
            {
                dynamic inserted = page.Drop(_replacementMaster, centerX / 25.4, centerY / 25.4);
                if (inserted == null)
                    throw new InvalidOperationException("Visio не вернул вставленный shape");
                int insertedId = Convert.ToInt32(inserted.ID, CultureInfo.InvariantCulture);

                if (!HasEndpoint(inserted, "begin") || !HasEndpoint(inserted, "end"))
                    throw new InvalidOperationException(
                        "Master-образец не является совместимым 1-D оборудованием"
                    );
                string receiveEndpoint =
                    _replacementInsertSourceEndpoint == "begin" ? "end" : "begin";
                int liveReceiveRow = FindConnectionPointRowAtEndpoint(inserted, receiveEndpoint, 0.10);
                if (liveReceiveRow != _replacementInsertReceiveRow)
                    throw new InvalidOperationException(
                        "Port profile master изменился после Drop; автоматическая вставка остановлена"
                    );

                double nativeBeginX = GetMm(inserted, "BeginX");
                double nativeBeginY = GetMm(inserted, "BeginY");
                double nativeEndX = GetMm(inserted, "EndX");
                double nativeEndY = GetMm(inserted, "EndY");
                double nativeLength = Math.Sqrt(
                    Math.Pow(nativeEndX - nativeBeginX, 2) +
                    Math.Pow(nativeEndY - nativeBeginY, 2)
                );
                const double minLeadMm = 1.0;
                if (nativeLength < 0.5)
                    throw new InvalidOperationException("У master некорректная инженерная длина");
                if (nativeLength + 2.0 * minLeadMm > connectionLength)
                    throw new InvalidOperationException(
                        String.Format(
                            CultureInfo.CurrentCulture,
                            "Оборудование не помещается в выбранную связь: длина master {0:0.###} мм, " +
                            "доступно {1:0.###} мм. Нужна более длинная связь или другой аппарат.",
                            nativeLength,
                            connectionLength
                        )
                    );

                // Keep the master at its natural length and align it with the selected
                // connection. Begin -> End follows the original connection direction.
                double half = nativeLength / 2.0;
                double insertBeginX = centerX - ux * half;
                double insertBeginY = centerY - uy * half;
                double insertEndX = centerX + ux * half;
                double insertEndY = centerY + uy * half;
                SetMm(inserted, "BeginX", insertBeginX);
                SetMm(inserted, "BeginY", insertBeginY);
                SetMm(inserted, "EndX", insertEndX);
                SetMm(inserted, "EndY", insertEndY);
                SetCellIdentity(inserted, cellId);

                // Split the existing connector instead of deleting it. One side keeps
                // its original target; the other side terminates at the apparatus'
                // receive port. The apparatus' source endpoint takes the opposite
                // original target.
                DetachEndpoint(connection, "begin");
                DetachEndpoint(connection, "end");
                dynamic receiveShape = inserted;

                if (_replacementInsertSourceEndpoint == "begin")
                {
                    GlueEndpoint(
                        inserted,
                        "begin",
                        page.Shapes.ItemFromID(beginTarget.TargetId),
                        beginTarget.Row
                    );
                    GlueEndpoint(
                        connection,
                        "begin",
                        receiveShape,
                        _replacementInsertReceiveRow
                    );
                    GlueEndpoint(
                        connection,
                        "end",
                        page.Shapes.ItemFromID(endTarget.TargetId),
                        endTarget.Row
                    );
                }
                else
                {
                    GlueEndpoint(
                        inserted,
                        "end",
                        page.Shapes.ItemFromID(endTarget.TargetId),
                        endTarget.Row
                    );
                    GlueEndpoint(
                        connection,
                        "begin",
                        page.Shapes.ItemFromID(beginTarget.TargetId),
                        beginTarget.Row
                    );
                    GlueEndpoint(
                        connection,
                        "end",
                        receiveShape,
                        _replacementInsertReceiveRow
                    );
                }

                // Verify every newly-authored edge before leaving the UI callback.
                GlueTarget insertedSource = TryGetGlueTarget(
                    inserted,
                    _replacementInsertSourceEndpoint
                );
                if (insertedSource == null)
                    throw new InvalidOperationException("Не удалось подтвердить source-port вставленного аппарата");
                GlueTarget splitBegin = TryGetGlueTarget(connection, "begin");
                GlueTarget splitEnd = TryGetGlueTarget(connection, "end");
                if (splitBegin == null || splitEnd == null)
                    throw new InvalidOperationException("Не удалось подтвердить оба сегмента разрезанной связи");

                List<GlueEdgeInfo> expected = new List<GlueEdgeInfo>();
                expected.Add(new GlueEdgeInfo {
                    SourceId = cell.AnchorId,
                    Endpoint = cell.Endpoint,
                    TargetId = cell.BusTerminalId,
                    Row = cell.ConnectionRow
                });
                foreach (GlueEdgeInfo edge in internalGlue)
                {
                    if (edge.SourceId == connectionId) continue;
                    expected.Add(edge);
                }
                expected.Add(new GlueEdgeInfo {
                    SourceId = insertedId,
                    Endpoint = _replacementInsertSourceEndpoint,
                    TargetId = insertedSource.TargetId,
                    Row = insertedSource.Row
                });
                expected.Add(new GlueEdgeInfo {
                    SourceId = connectionId,
                    Endpoint = "begin",
                    TargetId = splitBegin.TargetId,
                    Row = splitBegin.Row
                });
                expected.Add(new GlueEdgeInfo {
                    SourceId = connectionId,
                    Endpoint = "end",
                    TargetId = splitEnd.TargetId,
                    Row = splitEnd.Row
                });

                List<int> expectedMembers = cell.MemberIds
                    .Concat(new[] { insertedId })
                    .Distinct()
                    .OrderBy(id => id)
                    .ToList();

                ReplacementCompletionState pending = new ReplacementCompletionState {
                    ReplacementId = insertedId,
                    CellId = cellId,
                    Xmm = centerX,
                    Ymm = centerY,
                    ExpectedMemberCount = cell.MemberIds.Count + 1,
                    ExpectedMemberIds = expectedMembers,
                    ExpectedGlue = expected,
                    SuccessPrefix = String.Format(
                        CultureInfo.CurrentCulture,
                        "✓ Оборудование вставлено в связь: {0}; исходная связь разрезана, длина аппарата {1:0.###} мм",
                        _replacementMasterName,
                        nativeLength
                    )
                };

                SelectIds(page, new[] { insertedId });
                commit = true;
                return ScheduleStableTopologyCompletion(page, pending);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        private int FindConnectionPointRowAtEndpoint(
            dynamic shape,
            string endpoint,
            double toleranceMm)
        {
            string xCell = endpoint == "begin" ? "BeginX" : "EndX";
            string yCell = endpoint == "begin" ? "BeginY" : "EndY";
            double endpointX = GetMm(shape, xCell);
            double endpointY = GetMm(shape, yCell);
            List<Tuple<int, double>> candidates = new List<Tuple<int, double>>();
            for (int row = 1; row <= 32; row++)
            {
                string xName = "Connections.X" + row.ToString(CultureInfo.InvariantCulture);
                string yName = "Connections.Y" + row.ToString(CultureInfo.InvariantCulture);
                if (!CellExists(shape, xName) || !CellExists(shape, yName)) continue;
                try
                {
                    double localX = (double)shape.CellsU(xName).ResultIU;
                    double localY = (double)shape.CellsU(yName).ResultIU;
                    double pageX = 0.0, pageY = 0.0;
                    shape.XYToPage(localX, localY, out pageX, out pageY);
                    double dx = pageX * 25.4 - endpointX;
                    double dy = pageY * 25.4 - endpointY;
                    double distance = Math.Sqrt(dx * dx + dy * dy);
                    if (distance <= toleranceMm)
                        candidates.Add(Tuple.Create(row, distance));
                }
                catch { }
            }
            if (candidates.Count == 0) return 0;
            candidates = candidates.OrderBy(item => item.Item2).ToList();
            if (candidates.Count > 1 &&
                Math.Abs(candidates[0].Item2 - candidates[1].Item2) < 0.01)
                return 0;
            return candidates[0].Item1;
        }

        private List<GlueEdgeInfo> BuildReplacementExpectedGlue(
            CellInfo cell,
            IEnumerable<GlueEdgeInfo> internalGlue,
            int oldId,
            int newId)
        {
            List<GlueEdgeInfo> expected = new List<GlueEdgeInfo>();

            // Bus anchor first. VTD may rewrite dependent internal formulas after it.
            expected.Add(new GlueEdgeInfo {
                SourceId = cell.AnchorId == oldId ? newId : cell.AnchorId,
                Endpoint = cell.Endpoint,
                TargetId = cell.BusTerminalId,
                Row = cell.ConnectionRow
            });

            foreach (GlueEdgeInfo edge in internalGlue)
            {
                expected.Add(new GlueEdgeInfo {
                    SourceId = edge.SourceId == oldId ? newId : edge.SourceId,
                    Endpoint = edge.Endpoint,
                    TargetId = edge.TargetId == oldId ? newId : edge.TargetId,
                    Row = edge.Row
                });
            }
            return expected;
        }

        private string ScheduleStableTopologyCompletion(
            dynamic page,
            ReplacementCompletionState pending)
        {
            string documentName = Convert.ToString(page.Document.Name, CultureInfo.InvariantCulture) ?? "";
            string pageNameU = "";
            try { pageNameU = Convert.ToString(page.NameU, CultureInfo.InvariantCulture) ?? ""; }
            catch { pageNameU = Convert.ToString(page.Name, CultureInfo.InvariantCulture) ?? ""; }
            string token = "topology:" + Guid.NewGuid().ToString("N");

            lock (_asyncSync)
            {
                if (_asyncPending)
                    throw new InvalidOperationException("Предыдущая операция EnergoLogic ещё завершается");
                CleanupTopologyHelperArtifacts();
                _pendingTopologyCycles = 0;
                _pendingStablePasses = 0;
                _asyncPending = true;
                _asyncToken = token;
                _asyncState = "pending";
                _asyncMessage = "Изменение выполнено. Ожидается финальная проверка электрических связей…";
                _pendingDocumentName = documentName;
                _pendingPageNameU = pageNameU;
                _pendingStates = null;
                _pendingReplacement = pending;
                _pendingFinalSelection = new List<int> { pending.ReplacementId };
                _pendingSuccessPrefix = pending.SuccessPrefix;
            }
            return "⏳ Изменение выполнено. EnergoLogic завершит электрические связи следующим шагом… token=" + token;
        }

        private bool SupportsNativeReplaceShape()
        {
            try
            {
                string version = Convert.ToString(App.Version, CultureInfo.InvariantCulture) ?? "";
                string majorText = version.Split('.')[0].Split(',')[0];
                int major;
                if (Int32.TryParse(majorText, NumberStyles.Integer, CultureInfo.InvariantCulture, out major))
                    return major >= 15;
            }
            catch { }
            return false;
        }

        private void EnsureReplaceTargetSafe(dynamic page, CellInfo cell, int targetId)
        {
            HashSet<int> members = new HashSet<int>(cell.MemberIds);
            Dictionary<int, int> childParent = BuildChildParentMap(page);
            foreach (int sourceId in TopLevelIds(page))
            {
                dynamic source = page.Shapes.ItemFromID(sourceId);
                foreach (string endpoint in new[] { "begin", "end" })
                {
                    GlueTarget glue = TryGetGlueTarget(source, endpoint);
                    if (glue == null) continue;
                    int owner = childParent.ContainsKey(glue.TargetId)
                        ? childParent[glue.TargetId]
                        : glue.TargetId;

                    if (sourceId == targetId)
                    {
                        if (members.Contains(owner)) continue;
                        if (targetId == cell.AnchorId &&
                            glue.TargetId == cell.BusTerminalId &&
                            glue.Row == cell.ConnectionRow)
                            continue;
                        throw new InvalidOperationException(
                            "Выбранное оборудование имеет внешнюю связь вне ячейки; безопасная замена запрещена"
                        );
                    }

                    if (!members.Contains(sourceId) && owner == targetId)
                        throw new InvalidOperationException(
                            "К выбранному оборудованию подключён внешний элемент вне ячейки; безопасная замена запрещена"
                        );

                    if (members.Contains(sourceId) && owner == targetId && glue.TargetId != targetId)
                        throw new InvalidOperationException(
                            "Оборудование использует вложенную connection point; для такой замены нужен отдельный mapping profile"
                        );
                }
            }
        }

        private int RestoreReplacementTopology(
            dynamic page,
            CellInfo cell,
            IEnumerable<GlueEdgeInfo> internalGlue,
            int oldId,
            int newId,
            dynamic replacement)
        {
            int restored = 0;

            // The bus anchor must be authoritative first; VTD may rewrite dependent
            // internal formulas when the anchor changes.
            if (oldId == cell.AnchorId)
            {
                GlueTarget anchorGlue = TryGetGlueTarget(replacement, cell.Endpoint);
                if (anchorGlue == null ||
                    anchorGlue.TargetId != cell.BusTerminalId ||
                    anchorGlue.Row != cell.ConnectionRow)
                {
                    GlueEndpointWithRetry(
                        replacement,
                        cell.Endpoint,
                        page.Shapes.ItemFromID(cell.BusTerminalId),
                        cell.ConnectionRow
                    );
                    restored++;
                }
            }
            else
            {
                dynamic anchor = page.Shapes.ItemFromID(cell.AnchorId);
                VerifyGlue(anchor, cell.Endpoint, cell.BusTerminalId, cell.ConnectionRow);
            }

            foreach (GlueEdgeInfo edge in internalGlue)
            {
                if (edge.SourceId != oldId && edge.TargetId != oldId) continue;
                int sourceId = edge.SourceId == oldId ? newId : edge.SourceId;
                int targetId = edge.TargetId == oldId ? newId : edge.TargetId;
                dynamic source = sourceId == newId ? replacement : page.Shapes.ItemFromID(sourceId);
                dynamic target = targetId == newId ? replacement : page.Shapes.ItemFromID(targetId);
                GlueTarget current = TryGetGlueTarget(source, edge.Endpoint);
                if (current != null && current.TargetId == targetId && current.Row == edge.Row)
                    continue;
                GlueEndpointWithRetry(source, edge.Endpoint, target, edge.Row);
                restored++;
            }
            return restored;
        }

        private void VerifyReplacementTopology(
            dynamic page,
            CellInfo cell,
            IEnumerable<GlueEdgeInfo> internalGlue,
            int oldId,
            int newId,
            dynamic replacement)
        {
            if (oldId == cell.AnchorId)
                VerifyGlue(replacement, cell.Endpoint, cell.BusTerminalId, cell.ConnectionRow);
            else
                VerifyGlue(page.Shapes.ItemFromID(cell.AnchorId), cell.Endpoint, cell.BusTerminalId, cell.ConnectionRow);

            foreach (GlueEdgeInfo edge in internalGlue)
            {
                int sourceId = edge.SourceId == oldId ? newId : edge.SourceId;
                int targetId = edge.TargetId == oldId ? newId : edge.TargetId;
                dynamic source = sourceId == newId ? replacement : page.Shapes.ItemFromID(sourceId);
                VerifyGlue(source, edge.Endpoint, targetId, edge.Row);
            }
        }

        internal string ExactOffset(double dx, double dy)
        {
            if (Math.Abs(dx) < 1e-9 && Math.Abs(dy) < 1e-9) throw new InvalidOperationException("Смещение не может быть нулевым");
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            EnsureNoExternalGlue(page, ids);
            List<GlueEdgeInfo> internalGlue = CaptureInternalGlue(page, ids);
            int scope = (int)app.BeginUndoScope("EnergoLogic: Точный сдвиг");
            bool commit = false;
            try
            {
                SelectIds(page, ids);
                app.ActiveWindow.Selection.Move(dx, dy, "mm");
                SettleVisioAfterGeometryChange();
                int restoredInternal = RestoreInternalGlue(page, internalGlue);
                VerifyInternalGlue(page, internalGlue);
                commit = true;
                return String.Format(CultureInfo.CurrentCulture, "✓ Точный сдвиг: X {0:0.###} мм, Y {1:0.###} мм. Внутренние Glue проверены, восстановлено: {2}.", dx, dy, restoredInternal);
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
            List<GlueEdgeInfo> internalGlue = CaptureInternalGlue(page, ids);
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
                    dynamic sourceSelection = app.ActiveWindow.Selection;
                    dynamic dup = sourceSelection.Duplicate();
                    if (dup == null) dup = app.ActiveWindow.Selection;
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
                    SettleVisioAfterGeometryChange();
                    string cellId = "cell:" + Guid.NewGuid().ToString("N");
                    foreach (int id in newIds) if (HasCellIdentity(page.Shapes.ItemFromID(id))) SetCellIdentity(page.Shapes.ItemFromID(id), cellId);
                    List<GlueEdgeInfo> duplicateGlue = CaptureInternalGlue(page, newIds);
                    if (duplicateGlue.Count != internalGlue.Count)
                        throw new InvalidOperationException("Visio потерял внутренние Glue при копировании по базовой точке; операция отменена");
                }
                else
                {
                    app.ActiveWindow.Selection.Move(dx, dy, "mm");
                    SettleVisioAfterGeometryChange();
                    RestoreInternalGlue(page, internalGlue);
                    VerifyInternalGlue(page, internalGlue);
                }
                commit = true;
                return String.Format(CultureInfo.CurrentCulture, "✓ {0} по базовой точке: ΔX {1:0.###} мм, ΔY {2:0.###} мм.", copy ? "Копирование" : "Перемещение", dx, dy);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string Coordinates()
        {
            dynamic page = App.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            List<string> rows = new List<string>();
            foreach (int id in ids)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                string label = SafeText(shape).Trim();
                if (String.IsNullOrWhiteSpace(label)) label = Convert.ToString(shape.Name, CultureInfo.CurrentCulture);
                rows.Add(String.Format(CultureInfo.CurrentCulture,
                    "#{0} {1}: X {2:0.###} мм; Y {3:0.###} мм",
                    id, label, GetMm(shape, "PinX"), GetMm(shape, "PinY")));
            }
            return "Координаты выделения:\r\n" + String.Join("\r\n", rows.ToArray());
        }

        internal string RenumberCell(string newDesignation)
        {
            string value = (newDesignation ?? "").Trim();
            if (value.Length == 0) throw new InvalidOperationException("Введите новое обозначение ячейки");
            if (value.Length > 64) throw new InvalidOperationException("Обозначение ячейки не должно быть длиннее 64 символов");
            if (!Regex.IsMatch(value, @"^[\p{L}\p{N}][\p{L}\p{N}\s._/()+\-]{0,63}$"))
                throw new InvalidOperationException("В обозначении допустимы буквы, цифры, пробел, точка, дефис, /, + и скобки");

            dynamic app = App;
            dynamic page = app.ActivePage;
            CellInfo cell = DiscoverCellFromSelection(page);
            dynamic anchor = page.Shapes.ItemFromID(cell.AnchorId);
            string oldDesignation = SafeText(anchor).Trim();
            if (String.IsNullOrWhiteSpace(oldDesignation))
                throw new InvalidOperationException("У anchor выбранной ячейки отсутствует текстовое обозначение");
            if (String.Equals(oldDesignation, value, StringComparison.CurrentCulture))
                throw new InvalidOperationException("Новое обозначение совпадает с текущим");

            HashSet<int> memberIds = new HashSet<int>(cell.MemberIds);
            for (int index = 1; index <= (int)page.Shapes.Count; index++)
            {
                dynamic candidate = page.Shapes.Item(index);
                int candidateId = (int)candidate.ID;
                if (memberIds.Contains(candidateId)) continue;
                string text = SafeText(candidate).Trim();
                if (String.Equals(text, value, StringComparison.CurrentCultureIgnoreCase))
                    throw new InvalidOperationException("Обозначение \"" + value + "\" уже используется shape " + candidateId);
            }

            string oldShort = ShortDesignation(oldDesignation);
            string newShort = ShortDesignation(value);
            int scope = (int)app.BeginUndoScope("EnergoLogic: Перенумеровать ячейку");
            bool commit = false;
            int changed = 0;
            try
            {
                foreach (int id in cell.MemberIds)
                {
                    dynamic shape = page.Shapes.ItemFromID(id);
                    string text = SafeText(shape);
                    if (String.IsNullOrEmpty(text)) continue;
                    string updated = text;
                    if (updated.IndexOf(oldDesignation, StringComparison.CurrentCulture) >= 0)
                        updated = updated.Replace(oldDesignation, value);
                    else if (!String.IsNullOrWhiteSpace(oldShort) &&
                             String.Equals(updated.Trim(), oldShort, StringComparison.CurrentCulture))
                        updated = PreserveOuterWhitespace(updated, newShort);
                    if (!String.Equals(updated, text, StringComparison.Ordinal))
                    {
                        shape.Text = updated;
                        changed++;
                    }
                }
                if (changed == 0)
                    throw new InvalidOperationException("В составе ячейки не найдено текстов для перенумерации");
                if (!String.Equals(SafeText(anchor).Trim(), value, StringComparison.CurrentCulture))
                    throw new InvalidOperationException("После перенумерации anchor не получил новое обозначение");
                SelectIds(page, cell.MemberIds);
                commit = true;
                return String.Format(CultureInfo.CurrentCulture,
                    "✓ Ячейка перенумерована: {0} → {1}. Обновлено подписей: {2}. Identity сохранена.",
                    oldDesignation, value, changed);
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        private string ShortDesignation(string designation)
        {
            Match match = Regex.Match(designation ?? "", @"^(?<base>.+)-(?<voltage>\d+(?:[.,]\d+)?)$");
            return match.Success ? match.Groups["base"].Value : designation;
        }

        private string PreserveOuterWhitespace(string original, string replacement)
        {
            int start = 0;
            while (start < original.Length && Char.IsWhiteSpace(original[start])) start++;
            int end = original.Length - 1;
            while (end >= start && Char.IsWhiteSpace(original[end])) end--;
            string prefix = original.Substring(0, start);
            string suffix = end + 1 < original.Length ? original.Substring(end + 1) : "";
            return prefix + replacement + suffix;
        }

        internal string Align(string axis)
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count < 2) throw new InvalidOperationException("Для выравнивания выберите минимум два элемента");
            EnsureNoExternalGlue(page, ids);
            List<GlueEdgeInfo> internalGlue = CaptureInternalGlue(page, ids);
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
                SettleVisioAfterGeometryChange();
                RestoreInternalGlue(page, internalGlue);
                VerifyInternalGlue(page, internalGlue);
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
            List<CellMoveState> plan = new List<CellMoveState>();
            HashSet<int> selectedMembers = new HashSet<int>(cells.SelectMany(c => c.MemberIds));
            for (int i = 0; i < cells.Count; i++)
            {
                CellInfo cell = cells[i];
                dynamic target = GetBusTerminalBySlot(page, busId, startSlot + i);
                if (i > 0)
                {
                    dynamic prev = GetBusTerminalBySlot(page, busId, startSlot + i - 1);
                    double actual = Math.Abs(GetMm(target, "PinX") - GetMm(prev, "PinX"));
                    if (Math.Abs(actual - pitch) > 0.25)
                        throw new InvalidOperationException(String.Format(CultureInfo.CurrentCulture, "Шина имеет шаг {0:0.###} мм, а задан {1:0.###} мм", actual, pitch));
                }
                EnsureTerminalFree(page, (int)target.ID, selectedMembers);
                if ((int)target.ID == cell.BusTerminalId) continue;
                dynamic sourceTerminal = page.Shapes.ItemFromID(cell.BusTerminalId);
                plan.Add(new CellMoveState {
                    Cell = cell,
                    TargetTerminalId = (int)target.ID,
                    Dx = GetMm(target, "PinX") - GetMm(sourceTerminal, "PinX"),
                    Dy = GetMm(target, "PinY") - GetMm(sourceTerminal, "PinY"),
                    InternalGlue = CaptureInternalGlue(page, cell.MemberIds)
                });
            }

            if (plan.Count == 0)
            {
                SelectIds(page, cells.SelectMany(c => c.MemberIds).Distinct().ToList());
                return "✓ Ячейки уже распределены по реальным точкам шины. Шаг: " + pitch.ToString("0.###", CultureInfo.CurrentCulture) + " мм.";
            }

            int scope = (int)app.BeginUndoScope("EnergoLogic: Геометрия распределения ячеек");
            bool geometryCommit = false;
            try
            {
                foreach (CellMoveState state in plan)
                {
                    dynamic anchor = page.Shapes.ItemFromID(state.Cell.AnchorId);
                    DetachEndpoint(anchor, state.Cell.Endpoint);
                    SelectIds(page, state.Cell.MemberIds);
                    app.ActiveWindow.Selection.Move(state.Dx, state.Dy, "mm");
                }
                geometryCommit = true;
            }
            finally
            {
                app.EndUndoScope(scope, geometryCommit);
            }

            if (!geometryCommit)
                throw new InvalidOperationException("Геометрия распределения ячеек не была завершена");

            List<int> finalSelection = cells.SelectMany(c => c.MemberIds).Distinct().ToList();
            string successPrefix = String.Format(CultureInfo.CurrentCulture,
                "✓ Ячейки распределены по реальным точкам шины. Шаг: {0:0.###} мм. Перемещено: {1}",
                pitch, plan.Count);
            return ScheduleTopologyCompletion(page, plan, finalSelection, successPrefix);
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
                GlueEndpointWithRetry(shape, best.Item1, page.Shapes.ItemFromID(best.Item2.ShapeId), best.Item2.Row);
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

        internal string BusDiagnostics()
        {
            dynamic page = App.ActivePage;
            dynamic bus = ResolveSelectedBus(page);
            int busId = Convert.ToInt32(bus.ID, CultureInfo.InvariantCulture);
            int pointCount = GetBusPointCount(bus);
            double pitch = GetBusPitchMm(bus);
            double width = GetMm(bus, "Width");

            SortedDictionary<int, int> terminals = GetActiveBusTerminals(bus);
            List<string> structural = new List<string>();
            if (terminals.Count != pointCount)
                structural.Add(
                    "активных terminal " + terminals.Count +
                    ", Shape Data ожидает " + pointCount
                );
            for (int slot = 1; slot <= pointCount; slot++)
                if (!terminals.ContainsKey(slot))
                    structural.Add("не найден slot " + slot);

            Dictionary<int, List<int>> occupancy = new Dictionary<int, List<int>>();
            foreach (int slot in terminals.Keys)
                occupancy[slot] = new List<int>();

            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic shape = page.Shapes.Item(i);
                int sourceId = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture);
                if (sourceId == busId) continue;
                foreach (string endpoint in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, endpoint);
                    if (target == null) continue;
                    foreach (KeyValuePair<int, int> pair in terminals)
                    {
                        if (pair.Value == target.TargetId)
                            occupancy[pair.Key].Add(sourceId);
                    }
                }
            }

            List<string> free = occupancy
                .Where(pair => pair.Value.Count == 0)
                .Select(pair => pair.Key.ToString(CultureInfo.InvariantCulture))
                .ToList();
            List<string> occupied = occupancy
                .Where(pair => pair.Value.Count > 0)
                .Select(pair =>
                    pair.Key.ToString(CultureInfo.InvariantCulture) +
                    "→" + String.Join(",", pair.Value.Distinct().OrderBy(x => x))
                )
                .ToList();

            string prefix = structural.Count == 0 ? "✓" : "⚠";
            string result = String.Format(
                CultureInfo.CurrentCulture,
                "{0} Шина {1} (shape {2}): точек {3}; шаг {4:0.###} мм; ширина {5:0.###} мм. " +
                "Занято: [{6}]. Свободно: [{7}].",
                prefix,
                SafeText(bus).Replace("
", " ").Replace("
", " ").Trim(),
                busId,
                pointCount,
                pitch,
                width,
                String.Join("; ", occupied.ToArray()),
                String.Join(", ", free.ToArray())
            );
            if (structural.Count > 0)
                result += "
Structural: " + String.Join("; ", structural.ToArray());
            return result;
        }

        internal string ExtendBusRight()
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            dynamic bus = ResolveSelectedBus(page);
            int busId = Convert.ToInt32(bus.ID, CultureInfo.InvariantCulture);
            int current = GetBusPointCount(bus);
            if (current >= 10)
                throw new InvalidOperationException("VTD master поддерживает максимум 10 точек подключения");

            double oldPitch = GetBusPitchMm(bus);
            SortedDictionary<int, int> before = GetActiveBusTerminals(bus);

            int scope = (int)app.BeginUndoScope("EnergoLogic: Расширить шину вправо");
            bool commit = false;
            try
            {
                SetBusPointCount(bus, current + 1);
                SettleVisioAfterGeometryChange();

                if (GetBusPointCount(bus) != current + 1)
                    throw new InvalidOperationException("Shape Data шины не приняла новое количество точек");
                if (Math.Abs(GetBusPitchMm(bus) - oldPitch) > 0.01)
                    throw new InvalidOperationException("При расширении неожиданно изменился шаг шины");

                dynamic newTerminal = GetBusTerminalBySlot(page, busId, current + 1);
                int newSlot = GetSlot(newTerminal);
                if (newSlot != current + 1)
                    throw new InvalidOperationException("Новый terminal получил неверный номер места");
                EnsureTerminalFree(page, Convert.ToInt32(newTerminal.ID, CultureInfo.InvariantCulture), new HashSet<int>());

                SortedDictionary<int, int> after = GetActiveBusTerminals(bus);
                foreach (KeyValuePair<int, int> pair in before)
                    if (!after.ContainsKey(pair.Key) || after[pair.Key] != pair.Value)
                        throw new InvalidOperationException("При расширении изменилась identity существующего bus terminal");

                commit = true;
                return String.Format(
                    CultureInfo.CurrentCulture,
                    "✓ Шина расширена вправо: {0} → {1} точек; шаг {2:0.###} мм; новый slot {3}.",
                    current,
                    current + 1,
                    oldPitch,
                    newSlot
                );
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string TrimBusRight()
        {
            dynamic app = App;
            dynamic page = app.ActivePage;
            dynamic bus = ResolveSelectedBus(page);
            int busId = Convert.ToInt32(bus.ID, CultureInfo.InvariantCulture);
            int current = GetBusPointCount(bus);
            if (current <= 1)
                throw new InvalidOperationException("Нельзя уменьшить шину меньше одной точки подключения");

            dynamic lastTerminal = GetBusTerminalBySlot(page, busId, current);
            int lastTerminalId = Convert.ToInt32(lastTerminal.ID, CultureInfo.InvariantCulture);
            EnsureTerminalFree(page, lastTerminalId, new HashSet<int>());

            double oldPitch = GetBusPitchMm(bus);
            SortedDictionary<int, int> before = GetActiveBusTerminals(bus);

            int scope = (int)app.BeginUndoScope("EnergoLogic: Обрезать шину справа");
            bool commit = false;
            try
            {
                SetBusPointCount(bus, current - 1);
                SettleVisioAfterGeometryChange();

                if (GetBusPointCount(bus) != current - 1)
                    throw new InvalidOperationException("Shape Data шины не приняла уменьшение количества точек");
                if (Math.Abs(GetBusPitchMm(bus) - oldPitch) > 0.01)
                    throw new InvalidOperationException("При обрезке неожиданно изменился шаг шины");

                SortedDictionary<int, int> after = GetActiveBusTerminals(bus);
                if (after.ContainsKey(current))
                    throw new InvalidOperationException("Последний terminal остался активным после обрезки");
                for (int slot = 1; slot < current; slot++)
                    if (!after.ContainsKey(slot) || !before.ContainsKey(slot) || after[slot] != before[slot])
                        throw new InvalidOperationException("При обрезке изменилась identity существующего bus terminal");

                commit = true;
                return String.Format(
                    CultureInfo.CurrentCulture,
                    "✓ Шина обрезана справа: {0} → {1} точек; удалён свободный slot {2}.",
                    current,
                    current - 1,
                    current
                );
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string ReconnectEndpoint(string endpoint)
        {
            endpoint = (endpoint ?? "").Trim().ToLowerInvariant();
            if (endpoint != "begin" && endpoint != "end")
                throw new ArgumentException("endpoint должен быть begin или end");

            dynamic app = App;
            dynamic page = app.ActivePage;
            List<int> ids = CurrentTopLevelSelection(page);
            if (ids.Count != 1)
                throw new InvalidOperationException("Для Reconnect выберите один 1-D элемент");
            int sourceId = ids[0];
            dynamic source = page.Shapes.ItemFromID(sourceId);
            if (!HasEndpoint(source, endpoint))
                throw new InvalidOperationException("У выбранного элемента нет endpoint " + endpoint);

            double x = GetMm(source, endpoint == "begin" ? "BeginX" : "EndX");
            double y = GetMm(source, endpoint == "begin" ? "BeginY" : "EndY");
            GlueTarget current = TryGetGlueTarget(source, endpoint);
            Dictionary<int, int> childParent = BuildChildParentMap(page);

            List<ConnectionPointInfo> candidates = new List<ConnectionPointInfo>();
            foreach (ConnectionPointInfo p in GetAllConnectionPoints(page))
            {
                if (p.ShapeId == sourceId) continue;

                int owner;
                if (childParent.TryGetValue(p.ShapeId, out owner))
                {
                    try
                    {
                        dynamic parent = page.Shapes.ItemFromID(owner);
                        if (CellExists(parent, "Prop.tp") && CellExists(parent, "Prop.rt"))
                        {
                            try { GetSlot(page.Shapes.ItemFromID(p.ShapeId)); }
                            catch { continue; } // hidden/inactive VTD bus terminal
                        }
                    }
                    catch { }
                }

                double dx = p.Xmm - x;
                double dy = p.Ymm - y;
                double distance = Math.Sqrt(dx * dx + dy * dy);
                if (distance <= 1.0)
                    candidates.Add(new ConnectionPointInfo {
                        ShapeId = p.ShapeId,
                        Row = p.Row,
                        Xmm = p.Xmm,
                        Ymm = p.Ymm,
                        DistanceMm = distance
                    });
            }

            candidates = candidates.OrderBy(item => item.DistanceMm).ToList();
            if (candidates.Count == 0)
                throw new InvalidOperationException(
                    "Рядом с endpoint не найдено активной connection point (≤ 1 мм)"
                );
            if (candidates.Count > 1 &&
                Math.Abs(candidates[0].DistanceMm - candidates[1].DistanceMm) < 0.05)
                throw new InvalidOperationException(
                    "Reconnect неоднозначен: найдено несколько одинаково близких connection point"
                );

            ConnectionPointInfo best = candidates[0];
            if (current != null &&
                current.TargetId == best.ShapeId &&
                current.Row == best.Row)
                return String.Format(
                    CultureInfo.CurrentCulture,
                    "✓ {0} уже подключён к shape {1}/Connections.{2}.",
                    endpoint,
                    best.ShapeId,
                    best.Row
                );

            int scope = (int)app.BeginUndoScope("EnergoLogic: Reconnect " + endpoint);
            bool commit = false;
            try
            {
                if (current != null) DetachEndpoint(source, endpoint);
                dynamic target = page.Shapes.ItemFromID(best.ShapeId);
                GlueEndpointWithRetry(source, endpoint, target, best.Row);
                VerifyGlue(source, endpoint, best.ShapeId, best.Row);
                commit = true;
                string previous = current == null
                    ? "none"
                    : current.TargetId + "/Connections." + current.Row;
                return String.Format(
                    CultureInfo.CurrentCulture,
                    "✓ Reconnect {0}: {1} → {2}/Connections.{3}; расстояние {4:0.###} мм.",
                    endpoint,
                    previous,
                    best.ShapeId,
                    best.Row,
                    best.DistanceMm
                );
            }
            finally { app.EndUndoScope(scope, commit); }
        }

        internal string VisualDiagnostics()
        {
            dynamic page = App.ActivePage;
            List<ConnectionPointInfo> points = GetAllConnectionPoints(page);
            HashSet<string> connectedEndpoints = BuildConnectedEndpointIndex(page);
            HashSet<int> problemIds = new HashSet<int>();
            List<string> messages = new List<string>();

            // Visual touch without real Glue.
            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic shape = page.Shapes.Item(i);
                int id = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture);
                foreach (string endpoint in new[] { "begin", "end" })
                {
                    if (!HasEndpoint(shape, endpoint) ||
                        connectedEndpoints.Contains(EndpointKey(id, endpoint)))
                        continue;
                    double x = GetMm(shape, endpoint == "begin" ? "BeginX" : "EndX");
                    double y = GetMm(shape, endpoint == "begin" ? "BeginY" : "EndY");
                    bool near = points.Any(p =>
                        p.ShapeId != id &&
                        Math.Sqrt(Math.Pow(p.Xmm - x, 2) + Math.Pow(p.Ymm - y, 2)) <= 0.8
                    );
                    if (near)
                    {
                        problemIds.Add(id);
                        messages.Add("shape " + id + " " + endpoint + ": касание без Glue");
                    }
                }
            }

            // Bus structure and active terminal continuity.
            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic shape = page.Shapes.Item(i);
                if (!CellExists(shape, "Prop.tp") || !CellExists(shape, "Prop.rt")) continue;
                int id = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture);
                try
                {
                    int expected = GetBusPointCount(shape);
                    SortedDictionary<int, int> active = GetActiveBusTerminals(shape);
                    bool bad = active.Count != expected;
                    for (int slot = 1; slot <= expected; slot++)
                        if (!active.ContainsKey(slot)) bad = true;
                    if (bad)
                    {
                        problemIds.Add(id);
                        messages.Add(
                            "bus " + id + ": active terminals " + active.Count +
                            ", expected " + expected
                        );
                    }
                }
                catch (Exception ex)
                {
                    problemIds.Add(id);
                    messages.Add("bus " + id + ": " + ex.Message);
                }
            }

            // Persisted cell_id must resolve to exactly one bus anchor and a connected
            // member graph. Validate one representative per identity.
            Dictionary<string, int> identityRepresentative =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (int i = 1; i <= (int)page.Shapes.Count; i++)
            {
                dynamic shape = page.Shapes.Item(i);
                int id = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture);
                string identity = GetCellIdentity(shape);
                if (!String.IsNullOrWhiteSpace(identity) &&
                    !identityRepresentative.ContainsKey(identity))
                    identityRepresentative.Add(identity, id);
            }
            foreach (KeyValuePair<string, int> pair in identityRepresentative)
            {
                try { DiscoverCell(page, pair.Value); }
                catch (Exception ex)
                {
                    problemIds.Add(pair.Value);
                    messages.Add("cell " + pair.Key + ": " + ex.Message);
                }
            }

            if (problemIds.Count > 0)
                SelectIds(page, problemIds.OrderBy(id => id).ToList());

            if (messages.Count == 0)
                return String.Format(
                    CultureInfo.CurrentCulture,
                    "✓ Visual Diagnostics: structural-проблем не найдено. Проверено cell_id: {0}.",
                    identityRepresentative.Count
                );

            return "⚠ Visual Diagnostics: найдено проблем: " + messages.Count +
                ". Проблемные top-level элементы выделены.
" +
                String.Join("
", messages.Take(12).ToArray());
        }

        private dynamic ResolveSelectedBus(dynamic page)
        {
            List<int> selection = CurrentTopLevelSelection(page);
            if (selection.Count == 1)
            {
                dynamic selected = page.Shapes.ItemFromID(selection[0]);
                if (CellExists(selected, "Prop.tp") && CellExists(selected, "Prop.rt"))
                    return selected;
            }

            CellInfo cell = DiscoverCellFromSelection(page);
            dynamic bus = page.Shapes.ItemFromID(cell.BusId);
            if (!CellExists(bus, "Prop.tp") || !CellExists(bus, "Prop.rt"))
                throw new InvalidOperationException("Шина ячейки не поддерживает VTD Shape Data tp/rt");
            return bus;
        }

        private int GetBusPointCount(dynamic bus)
        {
            if (!CellExists(bus, "Prop.tp"))
                throw new InvalidOperationException("У шины отсутствует Prop.tp");
            int count = Convert.ToInt32(
                Math.Round((double)bus.CellsU("Prop.tp").ResultIU),
                CultureInfo.InvariantCulture
            );
            if (count < 1 || count > 10)
                throw new InvalidOperationException("Некорректное количество точек подключения шины: " + count);
            return count;
        }

        private double GetBusPitchMm(dynamic bus)
        {
            if (!CellExists(bus, "Prop.rt"))
                throw new InvalidOperationException("У шины отсутствует Prop.rt");
            return (double)bus.CellsU("Prop.rt").ResultIU * 25.4;
        }

        private void SetBusPointCount(dynamic bus, int count)
        {
            if (count < 1 || count > 10)
                throw new ArgumentOutOfRangeException("count");
            bus.CellsU("Prop.tp").FormulaU =
                "INDEX(" + (count - 1).ToString(CultureInfo.InvariantCulture) +
                ",Prop.tp.Format)";
        }

        private SortedDictionary<int, int> GetActiveBusTerminals(dynamic bus)
        {
            SortedDictionary<int, int> result = new SortedDictionary<int, int>();
            for (int i = 1; i <= (int)bus.Shapes.Count; i++)
            {
                dynamic child = bus.Shapes.Item(i);
                int slot;
                try { slot = GetSlot(child); }
                catch { continue; }
                if (result.ContainsKey(slot))
                    throw new InvalidOperationException("На шине дублируется slot " + slot);
                result.Add(slot, Convert.ToInt32(child.ID, CultureInfo.InvariantCulture));
            }
            return result;
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
            if (!top.Contains(selectedId))
                throw new InvalidOperationException("Выбранный объект не является top-level элементом схемы");

            string explicitCellId = GetCellIdentity(page.Shapes.ItemFromID(selectedId));
            if (!String.IsNullOrWhiteSpace(explicitCellId))
                return DiscoverCellByIdentity(page, selectedId, explicitCellId, childParent, top);

            Dictionary<int, HashSet<int>> graph = new Dictionary<int, HashSet<int>>();
            foreach (int id in top) graph[id] = new HashSet<int>();
            foreach (int id in top)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, ep);
                    if (target == null) continue;
                    int graphTargetId = target.TargetId;
                    int parentId;
                    if (childParent.TryGetValue(graphTargetId, out parentId))
                    {
                        // A numbered child connection point belongs to a bus and is
                        // an external cell boundary. Any other child connection point
                        // belongs to an equipment group; normalize it to that top-level
                        // owner so incoming Glue (for example RU SN -> transformer child)
                        // participates in the same logical cell.
                        if (IsNumberedBusTerminal(page, graphTargetId))
                            continue;
                        graphTargetId = parentId;
                    }
                    if (top.Contains(graphTargetId) && graphTargetId != id)
                    {
                        graph[id].Add(graphTargetId);
                        graph[graphTargetId].Add(id);
                    }
                }
            }
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
                    int parentId = 0;
                    if (target != null && childParent.TryGetValue(target.TargetId, out parentId) &&
                        IsNumberedBusTerminal(page, target.TargetId))
                        anchors.Add(Tuple.Create(id, target, parentId));
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

        private CellInfo DiscoverCellByIdentity(
            dynamic page,
            int selectedId,
            string cellId,
            Dictionary<int, int> childParent,
            HashSet<int> top)
        {
            List<int> members = new List<int>();
            foreach (int id in top)
            {
                string candidateId = GetCellIdentity(page.Shapes.ItemFromID(id));
                if (String.Equals(candidateId, cellId, StringComparison.OrdinalIgnoreCase))
                    members.Add(id);
            }
            members.Sort();
            if (members.Count == 0 || !members.Contains(selectedId))
                throw new InvalidOperationException("EnergoLogicCellId не разрешается в состав выбранной ячейки");

            HashSet<int> memberSet = new HashSet<int>(members);
            Dictionary<int, HashSet<int>> graph = new Dictionary<int, HashSet<int>>();
            foreach (int id in members) graph[id] = new HashSet<int>();

            List<Tuple<int, GlueTarget, int>> anchors = new List<Tuple<int, GlueTarget, int>>();
            foreach (int id in members)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                foreach (string ep in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(shape, ep);
                    if (target == null) continue;

                    int parentId = 0;
                    if (childParent.TryGetValue(target.TargetId, out parentId) &&
                        IsNumberedBusTerminal(page, target.TargetId))
                    {
                        anchors.Add(Tuple.Create(id, target, parentId));
                        continue;
                    }

                    int graphTargetId = target.TargetId;
                    if (childParent.TryGetValue(graphTargetId, out parentId))
                        graphTargetId = parentId;
                    if (memberSet.Contains(graphTargetId) && graphTargetId != id)
                    {
                        graph[id].Add(graphTargetId);
                        graph[graphTargetId].Add(id);
                    }
                }
            }

            if (anchors.Count != 1)
                throw new InvalidOperationException(
                    "Ячейка с identity " + cellId +
                    " должна иметь ровно один внешний Glue к шине; найдено: " + anchors.Count
                );

            var anchor = anchors[0];
            HashSet<int> core = new HashSet<int>();
            Stack<int> stack = new Stack<int>();
            stack.Push(anchor.Item1);
            while (stack.Count > 0)
            {
                int cur = stack.Pop();
                if (!core.Add(cur)) continue;
                foreach (int next in graph[cur])
                    if (!core.Contains(next)) stack.Push(next);
            }

            dynamic terminal = page.Shapes.ItemFromID(anchor.Item2.TargetId);
            return new CellInfo {
                AnchorId = anchor.Item1,
                BusId = anchor.Item3,
                BusTerminalId = anchor.Item2.TargetId,
                Slot = GetSlot(terminal),
                ConnectionRow = anchor.Item2.Row,
                Endpoint = anchor.Item2.Endpoint,
                CoreIds = core.OrderBy(x => x).ToList(),
                MemberIds = members
            };
        }

        private bool IsNumberedBusTerminal(dynamic page, int shapeId)
        {
            try
            {
                dynamic shape = page.Shapes.ItemFromID(shapeId);
                return GetSlot(shape) > 0;
            }
            catch { return false; }
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
            if (Int32.TryParse(
                    SafeText(terminal).Trim(),
                    NumberStyles.Integer,
                    CultureInfo.InvariantCulture,
                    out slot) &&
                slot > 0)
                return slot;

            // VTD bus master pre-creates hidden connection-point children. When
            // Prop.tp activates a new one, its Text can lag, while User.nt/ut are
            // authoritative immediately: active when ut=FALSE, slot=nt+1.
            try
            {
                if (CellExists(terminal, "User.nt") && CellExists(terminal, "User.ut"))
                {
                    bool hidden = Math.Abs((double)terminal.CellsU("User.ut").ResultIU) > 0.5;
                    if (!hidden)
                    {
                        int nt = Convert.ToInt32(
                            Math.Round((double)terminal.CellsU("User.nt").ResultIU),
                            CultureInfo.InvariantCulture
                        );
                        if (nt >= 0) return nt + 1;
                    }
                }
            }
            catch { }

            throw new InvalidOperationException("У connection point шины отсутствует активный номер места");
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
                AddDescendantOwners(top, (int)top.ID, map);
            }
            return map;
        }

        private void AddDescendantOwners(dynamic container, int topLevelOwnerId, Dictionary<int, int> map)
        {
            try
            {
                for (int index = 1; index <= (int)container.Shapes.Count; index++)
                {
                    dynamic child = container.Shapes.Item(index);
                    int childId = (int)child.ID;
                    map[childId] = topLevelOwnerId;
                    AddDescendantOwners(child, topLevelOwnerId, map);
                }
            }
            catch { }
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
            // after GlueTo. Read the source ShapeSheet formula directly.
            return TryGetGlueTargetFromFormula(shape, endpoint);
        }

        private GlueTarget TryGetGlueTargetFromFormula(dynamic shape, string endpoint)
        {
            if (!HasEndpoint(shape, endpoint)) return null;
            string sourceCellName = endpoint == "begin" ? "BeginX" : "EndX";
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

        private string ScheduleTopologyCompletion(dynamic page, List<CellMoveState> states, List<int> finalSelection, string successPrefix)
        {
            string documentName = Convert.ToString(page.Document.Name, CultureInfo.InvariantCulture) ?? "";
            string pageNameU = "";
            try { pageNameU = Convert.ToString(page.NameU, CultureInfo.InvariantCulture) ?? ""; }
            catch { pageNameU = Convert.ToString(page.Name, CultureInfo.InvariantCulture) ?? ""; }
            string token = "topology:" + Guid.NewGuid().ToString("N");
            lock (_asyncSync)
            {
                if (_asyncPending)
                    throw new InvalidOperationException("Предыдущая операция EnergoLogic ещё завершается");
                CleanupTopologyHelperArtifacts();
                _pendingTopologyCycles = 0;
                _pendingStablePasses = 0;
                _asyncPending = true;
                _asyncToken = token;
                _asyncState = "pending";
                _asyncMessage = "Геометрия готова. Ожидается завершение электрических связей…";
                _pendingDocumentName = documentName;
                _pendingPageNameU = pageNameU;
                _pendingStates = new List<CellMoveState>(states);
                _pendingFinalSelection = new List<int>(finalSelection);
                _pendingSuccessPrefix = successPrefix;
            }
            return "⏳ Геометрия выполнена. EnergoLogic завершит электрические связи следующим шагом… token=" + token;
        }

        internal string CompletePendingTopology()
        {
            string documentName;
            string pageNameU;
            List<CellMoveState> states = null;
            ReplacementCompletionState replacement = null;
            List<int> finalSelection;
            string successPrefix;
            string token;

            lock (_asyncSync)
            {
                if (!_asyncPending || (_pendingStates == null && _pendingReplacement == null))
                    return "✓ Нет незавершённых операций EnergoLogic.";

                documentName = _pendingDocumentName;
                pageNameU = _pendingPageNameU;
                if (_pendingStates != null)
                    states = new List<CellMoveState>(_pendingStates);
                replacement = _pendingReplacement;
                finalSelection = new List<int>(_pendingFinalSelection ?? new List<int>());
                successPrefix = _pendingSuccessPrefix;
                token = _asyncToken;

                if (_pendingTopologyHelperProcess == null)
                {
                    if (replacement != null)
                        StartExternalExpectedGlueRestore(
                            documentName, pageNameU, replacement.ExpectedGlue, token
                        );
                    else
                        StartExternalTopologyRestore(documentName, pageNameU, states, token);

                    _asyncState = "external_restoring";
                    _asyncMessage = "Электрические связи восстанавливаются внешним COM-процессом…";
                    return "state=external_restoring; token=" + token + "; message=" + _asyncMessage;
                }

                if (!_pendingTopologyHelperProcess.HasExited)
                {
                    _asyncState = "external_restoring";
                    _asyncMessage = "Электрические связи восстанавливаются внешним COM-процессом…";
                    return "state=external_restoring; token=" + token + "; message=" + _asyncMessage;
                }

                _asyncState = "verifying";
                _asyncMessage = "Проверяются восстановленные электрические связи…";
            }

            string finalMessage;
            string finalState;
            try
            {
                int exitCode = _pendingTopologyHelperProcess.ExitCode;
                string helperResult = File.Exists(_pendingTopologyResultPath)
                    ? File.ReadAllText(_pendingTopologyResultPath, Encoding.UTF8)
                    : "";
                if (exitCode != 0 || !helperResult.StartsWith("PASS", StringComparison.Ordinal))
                    throw new InvalidOperationException(
                        "Внешний topology helper завершился с ошибкой: exit=" + exitCode +
                        "; result=" + helperResult
                    );
                int repairedByHelper = ParseTopologyHelperRepairCount(helperResult);

                int verifiedGlue = 0;

                if (replacement != null)
                {
                    // The external helper owns the complete post-callback topology
                    // truth and its stabilization window. Phase 1 already verified
                    // replacement geometry + identity before scheduling. Do not touch
                    // Visio at all after helper PASS; even read-only COM access can
                    // give VTD another callback opportunity after the clean window.
                    verifiedGlue = replacement.ExpectedGlue.Count;

                    int completedCycles;
                    int stablePasses;
                    lock (_asyncSync)
                    {
                        _pendingTopologyCycles++;
                        if (repairedByHelper == 0)
                            _pendingStablePasses++;
                        else
                            _pendingStablePasses = 0;
                        completedCycles = _pendingTopologyCycles;
                        stablePasses = _pendingStablePasses;

                        if (stablePasses < 2)
                        {
                            if (completedCycles >= 6)
                                throw new InvalidOperationException(
                                    "Topology replacement не стабилизировалась за 6 внешних циклов"
                                );

                            CleanupTopologyHelperArtifacts();
                            _asyncState = "stabilizing";
                            _asyncMessage = String.Format(
                                CultureInfo.CurrentCulture,
                                "Проверка стабилизации VTD: clean {0}/2, цикл {1}/6; последний repair: {2}.",
                                stablePasses,
                                completedCycles,
                                repairedByHelper
                            );
                            return "state=stabilizing; token=" + token + "; message=" + _asyncMessage;
                        }
                    }

                    finalState = "success";
                    finalMessage = successPrefix +
                        "; topology стабилизирована за " + completedCycles +
                        " внешних циклов; подряд clean-проверок: " + stablePasses +
                        "; проверено Glue: " + verifiedGlue + ".";
                }
                else
                {
                    dynamic livePage = ResolveLivePage(documentName, pageNameU);
                    int verifiedInternal = 0;
                    foreach (CellMoveState state in states)
                    {
                        VerifyInternalGlue(livePage, state.InternalGlue);
                        dynamic anchor = livePage.Shapes.ItemFromID(state.Cell.AnchorId);
                        VerifyGlue(anchor, state.Cell.Endpoint, state.TargetTerminalId, state.Cell.ConnectionRow);
                        verifiedInternal += state.InternalGlue.Count;
                    }
                    VerifyMovedCellsComplete(livePage, states);
                    SelectIds(livePage, finalSelection);
                    finalState = "success";
                    finalMessage = successPrefix +
                        "; внешним COM-процессом проверено внутренних Glue: " +
                        verifiedInternal + ".";
                }
            }
            catch (Exception topologyError)
            {
                finalState = "failed_needs_attention";
                finalMessage =
                    "⚠ Не удалось завершить электрические связи внешним COM-процессом. " +
                    "Изменение оставлено для диагностики; исходная страница не затронута. Причина: " +
                    topologyError.Message;
            }

            lock (_asyncSync)
            {
                _asyncPending = false;
                _asyncState = finalState;
                _asyncMessage = finalMessage;
                _pendingDocumentName = "";
                _pendingPageNameU = "";
                _pendingStates = null;
                _pendingReplacement = null;
                _pendingFinalSelection = null;
                _pendingSuccessPrefix = "";
                _pendingTopologyCycles = 0;
                _pendingStablePasses = 0;
                CleanupTopologyHelperArtifacts();
            }
            // The caller owns status rendering. In particular, never BeginInvoke
            // UI work after the last clean topology check: VTD can process that queued
            // UI callback after this method returns and rewrite a dependent Glue edge.
            return "state=" + finalState + "; token=" + token + "; message=" + finalMessage;
        }

        private void StartExternalTopologyRestore(
            string documentName,
            string pageNameU,
            IEnumerable<CellMoveState> states,
            string token)
        {
            List<GlueEdgeInfo> expected = new List<GlueEdgeInfo>();
            foreach (CellMoveState state in states)
            {
                expected.Add(new GlueEdgeInfo {
                    SourceId = state.Cell.AnchorId,
                    Endpoint = state.Cell.Endpoint,
                    TargetId = state.TargetTerminalId,
                    Row = state.Cell.ConnectionRow
                });
                foreach (GlueEdgeInfo edge in state.InternalGlue)
                    expected.Add(edge);
            }
            StartExternalExpectedGlueRestore(documentName, pageNameU, expected, token);
        }

        private void StartExternalExpectedGlueRestore(
            string documentName,
            string pageNameU,
            IEnumerable<GlueEdgeInfo> expectedEdges,
            string token)
        {
            string assemblyDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location) ?? "";
            string helperPath = Path.Combine(assemblyDir, "EnergoLogic.TopologyRestoreHelper.exe");
            if (!File.Exists(helperPath))
                throw new FileNotFoundException("Не найден внешний topology helper", helperPath);

            string suffix = token.Replace(":", "-");
            string tempDir = Path.GetTempPath();
            _pendingTopologyPlanPath = Path.Combine(tempDir, "energologic-" + suffix + ".plan");
            _pendingTopologyResultPath = Path.Combine(tempDir, "energologic-" + suffix + ".result");
            try { File.Delete(_pendingTopologyResultPath); } catch { }

            List<string> lines = new List<string>();
            lines.Add("DOC\t" + Convert.ToBase64String(Encoding.UTF8.GetBytes(documentName)));
            lines.Add("PAGE\t" + Convert.ToBase64String(Encoding.UTF8.GetBytes(pageNameU)));
            Dictionary<string, GlueEdgeInfo> unique =
                new Dictionary<string, GlueEdgeInfo>(StringComparer.OrdinalIgnoreCase);

            foreach (GlueEdgeInfo edge in expectedEdges)
            {
                string key = EndpointKey(edge.SourceId, edge.Endpoint);
                GlueEdgeInfo existing;
                if (unique.TryGetValue(key, out existing))
                {
                    if (existing.TargetId != edge.TargetId || existing.Row != edge.Row)
                        throw new InvalidOperationException(
                            "Topology plan contains conflicting targets for " + key
                        );
                    continue;
                }
                unique[key] = edge;
                lines.Add(String.Format(
                    CultureInfo.InvariantCulture,
                    "EDGE\t{0}\t{1}\t{2}\t{3}",
                    edge.SourceId,
                    edge.Endpoint,
                    edge.TargetId,
                    edge.Row
                ));
            }

            File.WriteAllLines(_pendingTopologyPlanPath, lines.ToArray(), Encoding.UTF8);

            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = helperPath;
            info.Arguments = QuoteProcessArgument(_pendingTopologyPlanPath) + " " +
                             QuoteProcessArgument(_pendingTopologyResultPath);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            _pendingTopologyHelperProcess = Process.Start(info);
            if (_pendingTopologyHelperProcess == null)
                throw new InvalidOperationException("Не удалось запустить внешний topology helper");
        }

        private int ParseTopologyHelperRepairCount(string helperResult)
        {
            try
            {
                string[] parts = (helperResult ?? "").Trim().Split('	');
                if (parts.Length >= 2 && String.Equals(parts[0], "PASS", StringComparison.Ordinal))
                {
                    int count;
                    if (Int32.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out count))
                        return Math.Max(0, count);
                }
            }
            catch { }
            throw new InvalidOperationException("Некорректный результат topology helper: " + helperResult);
        }

        private string QuoteProcessArgument(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
        }

        private void CleanupTopologyHelperArtifacts()
        {
            try { if (_pendingTopologyHelperProcess != null) _pendingTopologyHelperProcess.Dispose(); } catch { }
            _pendingTopologyHelperProcess = null;
            try { if (!String.IsNullOrWhiteSpace(_pendingTopologyPlanPath)) File.Delete(_pendingTopologyPlanPath); } catch { }
            try { if (!String.IsNullOrWhiteSpace(_pendingTopologyResultPath)) File.Delete(_pendingTopologyResultPath); } catch { }
            _pendingTopologyPlanPath = "";
            _pendingTopologyResultPath = "";
        }

        private dynamic ResolveLivePage(string documentName, string pageNameU)
        {
            dynamic app = App;
            dynamic foundDocument = null;
            for (int documentIndex = 1; documentIndex <= (int)app.Documents.Count; documentIndex++)
            {
                dynamic candidate = app.Documents.Item(documentIndex);
                string candidateName = "";
                try { candidateName = Convert.ToString(candidate.Name, CultureInfo.InvariantCulture) ?? ""; } catch { }
                if (String.Equals(candidateName, documentName, StringComparison.OrdinalIgnoreCase))
                {
                    foundDocument = candidate;
                    break;
                }
            }
            if (foundDocument == null)
                throw new InvalidOperationException("Документ операции больше не открыт: " + documentName);

            dynamic pages = foundDocument.Pages;
            for (int pageIndex = 1; pageIndex <= (int)pages.Count; pageIndex++)
            {
                dynamic candidatePage = pages.Item(pageIndex);
                string candidateNameU = "";
                string candidateName = "";
                try { candidateNameU = Convert.ToString(candidatePage.NameU, CultureInfo.InvariantCulture) ?? ""; } catch { }
                try { candidateName = Convert.ToString(candidatePage.Name, CultureInfo.InvariantCulture) ?? ""; } catch { }
                if (String.Equals(candidateNameU, pageNameU, StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(candidateName, pageNameU, StringComparison.OrdinalIgnoreCase))
                    return candidatePage;
            }
            throw new InvalidOperationException("Страница операции больше не найдена: " + pageNameU);
        }

        private void VerifyMovedCellsComplete(dynamic page, IEnumerable<CellMoveState> states)
        {
            foreach (CellMoveState state in states)
            {
                CellInfo rediscovered = DiscoverCell(page, state.Cell.AnchorId);
                if (rediscovered.MemberIds.Count != state.Cell.MemberIds.Count)
                    throw new InvalidOperationException(
                        "После перемещения состав ячейки " + state.Cell.AnchorId +
                        " изменился: было " + state.Cell.MemberIds.Count +
                        ", стало " + rediscovered.MemberIds.Count
                    );
            }
        }

        private int RestoreCellTopologyAfterMove(dynamic page, CellMoveState state)
        {
            int restored = RestoreInternalGlue(page, state.InternalGlue);
            dynamic anchor = page.Shapes.ItemFromID(state.Cell.AnchorId);
            dynamic target = page.Shapes.ItemFromID(state.TargetTerminalId);
            GlueEndpointWithRetry(anchor, state.Cell.Endpoint, target, state.Cell.ConnectionRow);
            VerifyInternalGlue(page, state.InternalGlue);
            return restored;
        }

        private string CompensateCellMoves(dynamic page, IList<CellMoveState> states)
        {
            List<string> failures = new List<string>();
            for (int index = states.Count - 1; index >= 0; index--)
            {
                CellMoveState state = states[index];
                try
                {
                    dynamic anchor = page.Shapes.ItemFromID(state.Cell.AnchorId);
                    try { DetachEndpoint(anchor, state.Cell.Endpoint); } catch { }
                    SelectIds(page, state.Cell.MemberIds);
                    App.ActiveWindow.Selection.Move(-state.Dx, -state.Dy, "mm");
                    SettleVisioAfterGeometryChange();
                    RestoreInternalGlue(page, state.InternalGlue);
                    dynamic originalTerminal = page.Shapes.ItemFromID(state.Cell.BusTerminalId);
                    GlueEndpointWithRetry(anchor, state.Cell.Endpoint, originalTerminal, state.Cell.ConnectionRow);
                    VerifyInternalGlue(page, state.InternalGlue);
                }
                catch (Exception ex)
                {
                    failures.Add("ячейка " + state.Cell.AnchorId + ": " + ex.Message);
                }
            }
            if (failures.Count == 0) return "Исходная геометрия и Glue восстановлены.";
            return "ВНИМАНИЕ: автоматическое восстановление исходной схемы неполное: " + String.Join(" | ", failures.ToArray()) + ".";
        }

        private void SettleVisioAfterGeometryChange()
        {
            // VTD/Visio can update endpoint formulas asynchronously after Selection.Move.
            // Pump the UI queue briefly before re-applying native Glue.
            for (int i = 0; i < 4; i++)
            {
                System.Windows.Forms.Application.DoEvents();
                System.Threading.Thread.Sleep(25);
            }
        }

        private List<GlueEdgeInfo> CaptureInternalGlue(dynamic page, IEnumerable<int> ids)
        {
            HashSet<int> members = new HashSet<int>(ids);
            Dictionary<int, int> childParent = BuildChildParentMap(page);
            List<GlueEdgeInfo> result = new List<GlueEdgeInfo>();
            foreach (int sourceId in members)
            {
                dynamic source = page.Shapes.ItemFromID(sourceId);
                foreach (string endpoint in new[] { "begin", "end" })
                {
                    GlueTarget target = TryGetGlueTarget(source, endpoint);
                    if (target == null) continue;
                    int owner = childParent.ContainsKey(target.TargetId) ? childParent[target.TargetId] : target.TargetId;
                    if (!members.Contains(owner)) continue;
                    result.Add(new GlueEdgeInfo {
                        SourceId = sourceId,
                        Endpoint = endpoint,
                        TargetId = target.TargetId,
                        Row = target.Row
                    });
                }
            }
            return result;
        }

        private int RestoreInternalGlue(dynamic page, IEnumerable<GlueEdgeInfo> edges)
        {
            int restored = 0;
            foreach (GlueEdgeInfo edge in edges)
            {
                dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                GlueTarget current = TryGetGlueTarget(source, edge.Endpoint);
                if (current != null && current.TargetId == edge.TargetId && current.Row == edge.Row)
                    continue;
                dynamic target = page.Shapes.ItemFromID(edge.TargetId);
                GlueEndpointWithRetry(source, edge.Endpoint, target, edge.Row);
                restored++;
            }
            return restored;
        }

        private void VerifyInternalGlue(dynamic page, IEnumerable<GlueEdgeInfo> edges)
        {
            foreach (GlueEdgeInfo edge in edges)
            {
                dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                VerifyGlue(source, edge.Endpoint, edge.TargetId, edge.Row);
            }
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

        private void NormalizeEndpointPairForGlue(dynamic shape, string endpoint)
        {
            string xName = endpoint == "begin" ? "BeginX" : "EndX";
            string yName = endpoint == "begin" ? "BeginY" : "EndY";
            double x = GetMm(shape, xName);
            double y = GetMm(shape, yName);

            // VTD can leave a moved 1-D endpoint half-glued: X becomes a literal
            // while Y still contains PAR(PNT(...)). GlueTo from inside the add-in is
            // not reliable from that asymmetric state. Materialize both coordinates
            // immediately before every GlueTo attempt so the endpoint starts from one
            // coherent detached state without changing its visible position.
            SetMm(shape, xName, x);
            SetMm(shape, yName, y);
        }

        private void GlueEndpointWithRetry(dynamic shape, string endpoint, dynamic target, int row)
        {
            int targetId = Convert.ToInt32(target.ID, CultureInfo.InvariantCulture);
            Exception lastError = null;
            int previousEventsEnabled = 1;
            bool eventsSuppressed = false;
            try
            {
                // VTD reacts to the same cell mutations that GlueTo produces. In the
                // in-process COM add-in path that reaction can synchronously rewrite a
                // freshly glued EndX back to a literal while EndY remains referenced.
                // Visio documents EventsEnabled as the application-wide switch that
                // suppresses event firing/add-on execution. Keep the critical GlueTo
                // section bounded and restore the exact previous value in finally.
                previousEventsEnabled = Convert.ToInt32(App.EventsEnabled, CultureInfo.InvariantCulture);
                App.EventsEnabled = 0;
                eventsSuppressed = true;

                for (int attempt = 1; attempt <= 6; attempt++)
                {
                    try
                    {
                        NormalizeEndpointPairForGlue(shape, endpoint);
                        GlueEndpoint(shape, endpoint, target, row);

                        try
                        {
                            VerifyGlue(shape, endpoint, targetId, row);
                            return;
                        }
                        catch (Exception immediateError)
                        {
                            lastError = immediateError;
                        }

                        for (int pump = 0; pump < 2; pump++)
                        {
                            System.Windows.Forms.Application.DoEvents();
                            System.Threading.Thread.Sleep(25);
                            try
                            {
                                VerifyGlue(shape, endpoint, targetId, row);
                                return;
                            }
                            catch (Exception settleError)
                            {
                                lastError = settleError;
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        lastError = ex;
                    }
                }
            }
            finally
            {
                if (eventsSuppressed)
                {
                    try { App.EventsEnabled = previousEventsEnabled; } catch { }
                }
            }

            throw new InvalidOperationException(
                "Glue не стабилизировался после 6 event-isolated попыток: " +
                (lastError == null ? "неизвестная причина" : lastError.Message),
                lastError
            );
        }

        private void VerifyGlue(dynamic shape, string endpoint, int targetId, int row)
        {
            GlueTarget nativeTarget = TryGetGlueTarget(shape, endpoint);
            if (nativeTarget != null && nativeTarget.TargetId == targetId && nativeTarget.Row == row) return;

            // Immediately after GlueTo Visio can expose a stale Connects collection while
            // the ShapeSheet formula is already authoritative. Accept only an exact formula match.
            GlueTarget formulaTarget = TryGetGlueTargetFromFormula(shape, endpoint);
            if (formulaTarget != null && formulaTarget.TargetId == targetId && formulaTarget.Row == row) return;

            int sourceId = 0;
            try { sourceId = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture); } catch { }
            string sourceCell = endpoint == "begin" ? "BeginX" : "EndX";
            string formula = "";
            try { formula = Convert.ToString(shape.CellsU(sourceCell).FormulaU, CultureInfo.InvariantCulture) ?? ""; } catch { }
            string nativeText = nativeTarget == null ? "none" : nativeTarget.TargetId + "/" + nativeTarget.Row;
            string formulaText = formulaTarget == null ? "none" : formulaTarget.TargetId + "/" + formulaTarget.Row;
            throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                "Проверка Glue не прошла: source {0} {1}; expected {2}/{3}; native {4}; formulaTarget {5}; FormulaU={6}",
                sourceId, endpoint, targetId, row, nativeText, formulaText, formula));
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
            return !String.IsNullOrWhiteSpace(GetCellIdentity(shape));
        }

        private string CellIdentityPageCellName(int shapeId)
        {
            return "User.EnergoLogicCell_" + shapeId.ToString(CultureInfo.InvariantCulture);
        }

        private string FormulaStringValue(dynamic cell)
        {
            try
            {
                string formula = Convert.ToString(cell.FormulaU, CultureInfo.InvariantCulture) ?? "";
                formula = formula.Trim();
                if (formula.Length >= 2 && formula[0] == '"' && formula[formula.Length - 1] == '"')
                    return formula.Substring(1, formula.Length - 2).Replace("\"\"", "\"");
            }
            catch { }
            return "";
        }

        private string GetCellIdentity(dynamic shape)
        {
            // Production identity lives on PageSheet, not on electrical VTD shapes.
            // Writing User.* metadata into VTD apparatus can trigger its automation
            // and corrupt otherwise unrelated Glue. PageSheet keeps semantics outside
            // the electrical drawing objects while remaining persisted in Visio.
            try
            {
                dynamic page = shape.ContainingPage;
                if (page != null)
                {
                    dynamic pageSheet = page.PageSheet;
                    string cellName = CellIdentityPageCellName(
                        Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture)
                    );
                    if (CellExists(pageSheet, cellName))
                    {
                        string value = FormulaStringValue(pageSheet.CellsU(cellName));
                        if (!String.IsNullOrWhiteSpace(value)) return value;
                    }
                }
            }
            catch { }

            // Read-only compatibility with v3.19-v3.29 disposable pages.
            if (CellExists(shape, "User.EnergoLogicCellId"))
            {
                string legacy = FormulaStringValue(shape.CellsU("User.EnergoLogicCellId"));
                if (!String.IsNullOrWhiteSpace(legacy)) return legacy;
            }
            return "";
        }

        private void SetCellIdentity(dynamic shape, string cellId)
        {
            const short visSectionUser = 242;
            dynamic page = shape.ContainingPage;
            if (page == null)
                throw new InvalidOperationException("Shape не принадлежит странице Visio");
            dynamic pageSheet = page.PageSheet;
            object sectionExistsRaw = pageSheet.SectionExists(visSectionUser, 0);
            if (Convert.ToInt32(sectionExistsRaw, CultureInfo.InvariantCulture) == 0)
                pageSheet.AddSection(visSectionUser);

            int shapeId = Convert.ToInt32(shape.ID, CultureInfo.InvariantCulture);
            string rowName = "EnergoLogicCell_" + shapeId.ToString(CultureInfo.InvariantCulture);
            string cellName = "User." + rowName;
            if (!CellExists(pageSheet, cellName))
                pageSheet.AddNamedRow(visSectionUser, rowName, 0);
            pageSheet.CellsU(cellName).FormulaU = "\"" + (cellId ?? "").Replace("\"", "\"\"") + "\"";
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
        private readonly TextBox _renumber;
        private Timer _topologyTimer;

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
            Button bindIdentity = ButtonWide("Закрепить состав ячейки", (s,e)=>RunBindCellIdentity());
            cells.Controls.Add(bindIdentity,0,3);
            cells.SetColumnSpan(bindIdentity,2);
            cells.Controls.Add(Button("Запомнить образец", (s,e)=>Run(()=>_addin.CaptureReplacementSample())),0,4);
            cells.Controls.Add(Button("Заменить по образцу", (s,e)=>RunReplaceEquipment()),1,4);
            Button insertEquipment = ButtonWide("Вставить образец в связь", (s,e)=>RunInsertEquipment());
            cells.Controls.Add(insertEquipment,0,5);
            cells.SetColumnSpan(insertEquipment,2);
            _renumber = new TextBox { Dock=DockStyle.Fill, Margin=new Padding(5), AccessibleName="Новое обозначение ячейки" };
            cells.Controls.Add(_renumber,0,6);
            cells.Controls.Add(Button("Перенумеровать", (s,e)=>Run(()=>_addin.RenumberCell(_renumber.Text))),1,6);
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
            Button measure=Button("Измерить шаг",(s,e)=>RunPitchMeasure()); Button dist=Button("Распределить",(s,e)=>RunDistributePitch());
            geo.Controls.Add(measure,2,6); geo.Controls.Add(dist,3,6);
            Button nx=Button("← 1 мм",(s,e)=>Run(()=>_addin.ExactOffset(-1,0)));
            Button px=Button("1 мм →",(s,e)=>Run(()=>_addin.ExactOffset(1,0)));
            Button ny=Button("↓ 1 мм",(s,e)=>Run(()=>_addin.ExactOffset(0,-1)));
            Button py=Button("↑ 1 мм",(s,e)=>Run(()=>_addin.ExactOffset(0,1)));
            geo.Controls.Add(nx,0,7); geo.Controls.Add(px,1,7); geo.Controls.Add(ny,2,7); geo.Controls.Add(py,3,7);
            Button coords=ButtonWide("Показать координаты выделения",(s,e)=>Run(()=>_addin.Coordinates()));
            geo.Controls.Add(coords,0,8); geo.SetColumnSpan(coords,4);
            geoTab.Controls.Add(geo);

            FlowLayoutPanel checks = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, Padding = new Padding(14), WrapContents=false };
            checks.Controls.Add(ButtonWide("Визуальная диагностика", (s,e)=>Run(()=>_addin.VisualDiagnostics())));
            checks.Controls.Add(ButtonWide("Проверить схему", (s,e)=>Run(()=>_addin.Doctor())));
            checks.Controls.Add(ButtonWide("Диагностика шины", (s,e)=>Run(()=>_addin.BusDiagnostics())));
            checks.Controls.Add(ButtonWide("Расширить шину →", (s,e)=>Run(()=>_addin.ExtendBusRight())));
            checks.Controls.Add(ButtonWide("Обрезать шину справа", (s,e)=>Run(()=>_addin.TrimBusRight())));
            checks.Controls.Add(ButtonWide("Reconnect Begin", (s,e)=>Run(()=>_addin.ReconnectEndpoint("begin"))));
            checks.Controls.Add(ButtonWide("Reconnect End", (s,e)=>Run(()=>_addin.ReconnectEndpoint("end"))));
            checks.Controls.Add(new Label { AutoSize=true, MaximumSize=new Size(350,0), Text="Диагностика не перекрашивает схему: проблемные top-level элементы только выделяются. Extend/Trim используют штатные VTD Shape Data Prop.tp/Prop.rt." });
            checkTab.Controls.Add(checks);

            _status = new TextBox { Dock=DockStyle.Fill, Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Vertical, BackColor=SystemColors.Window, Text="EnergoLogic готов. Выберите объект на схеме и используйте команду выше." };
            _status.Name = "EnergoLogicStatus";
            _status.AccessibleName = "EnergoLogic status";
            Panel statusPanel = new Panel { Dock=DockStyle.Fill, Padding=new Padding(8) };
            statusPanel.Controls.Add(_status);

            Controls.Add(statusPanel);
            Controls.Add(tabs);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && _topologyTimer != null)
            {
                _topologyTimer.Stop();
                _topologyTimer.Dispose();
                _topologyTimer = null;
            }
            base.Dispose(disposing);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing) { e.Cancel=true; Hide(); return; }
            base.OnFormClosing(e);
        }

        public void SetStatus(string value)
        {
            if (InvokeRequired)
            {
                BeginInvoke((MethodInvoker)delegate { SetStatus(value); });
                return;
            }
            _status.Text = value ?? "";
        }

        private void Run(Func<string> action)
        {
            try { _status.Text = action(); }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void RunBindCellIdentity()
        {
            try
            {
                string result = _addin.BindCellIdentity();
                _status.Text = result;
                if (result.StartsWith("⏳", StringComparison.Ordinal))
                    StartTopologyCompletionTimer();
            }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void RunInsertEquipment()
        {
            try
            {
                string result = _addin.InsertEquipmentIntoConnectionFromSample();
                _status.Text = result;
                if (result.StartsWith("⏳", StringComparison.Ordinal))
                    StartTopologyCompletionTimer();
            }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void RunReplaceEquipment()
        {
            try
            {
                string result = _addin.ReplaceEquipmentFromSample();
                _status.Text = result;
                if (result.StartsWith("⏳", StringComparison.Ordinal))
                    StartTopologyCompletionTimer();
            }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void RunDistributePitch()
        {
            try
            {
                string result = _addin.DistributePitch((double)_pitch.Value);
                _status.Text = result;
                if (result.StartsWith("⏳", StringComparison.Ordinal))
                    StartTopologyCompletionTimer();
            }
            catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
        }

        private void StartTopologyCompletionTimer()
        {
            if (_topologyTimer != null)
            {
                _topologyTimer.Stop();
                _topologyTimer.Dispose();
            }
            _topologyTimer = new Timer { Interval = 350 };
            _topologyTimer.Tick += delegate
            {
                Timer timer = _topologyTimer;
                _topologyTimer = null;
                if (timer != null) { timer.Stop(); timer.Dispose(); }
                try
                {
                    string result = _addin.CompletePendingTopology();
                    _status.Text = result;
                    if (result.StartsWith("state=external_restoring", StringComparison.Ordinal) ||
                        result.StartsWith("state=stabilizing", StringComparison.Ordinal))
                        StartTopologyCompletionTimer();
                }
                catch(Exception ex) { _status.Text = "⚠ " + Friendly(ex); }
            };
            _topologyTimer.Start();
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
            TableLayoutPanel p=new TableLayoutPanel{Dock=DockStyle.Top,Height=365,ColumnCount=2,RowCount=7,Padding=new Padding(10)};
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50)); p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            return p;
        }
        private Button Button(string text, EventHandler h) { Button b=new Button{Text=text,Dock=DockStyle.Fill,Height=38,Margin=new Padding(5),AccessibleName=text}; b.Click+=h; return b; }
        private Button ButtonWide(string text, EventHandler h) { Button b=new Button{Text=text,Width=330,Height=38,Margin=new Padding(4),AccessibleName=text}; b.Click+=h; return b; }
        private NumericUpDown Num(decimal min, decimal max, decimal value) { return new NumericUpDown{Minimum=min,Maximum=max,Value=value,DecimalPlaces=2,Increment=0.5M,Dock=DockStyle.Fill}; }
    }
}
