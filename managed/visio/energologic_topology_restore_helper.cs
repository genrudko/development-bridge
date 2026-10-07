using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace EnergoLogicTopologyRestore
{
    internal sealed class Edge
    {
        public int SourceId;
        public string Endpoint;
        public int TargetId;
        public int Row;
    }

    internal sealed class ExplicitDetach
    {
        public int ShapeId;
        public string Endpoint;
    }

    internal sealed class MoveStep
    {
        public int AnchorId;
        public string Endpoint;
        public double DxMm;
        public double DyMm;
        public List<int> MemberIds = new List<int>();
    }

    internal sealed class GeometryExpectation
    {
        public int ShapeId;
        public string CellName;
        public double ExpectedMm;
        public string FormulaU;
    }

    internal static class Program
    {
        private static void Trace(string tracePath, string marker)
        {
            try
            {
                File.AppendAllText(
                    tracePath,
                    DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture) + "\t" +
                    marker + Environment.NewLine,
                    Encoding.UTF8
                );
            }
            catch { }
        }

        private static string Decode(string value)
        {
            return Encoding.UTF8.GetString(Convert.FromBase64String(value));
        }

        private static bool FormulaReferencesTarget(
            string formula,
            dynamic target,
            int row,
            string axis)
        {
            string value = formula ?? "";
            string rowText = row.ToString(CultureInfo.InvariantCulture);
            string[] suffixes = new[] {
                "!Connections." + rowText + "." + axis,
                "!Connections." + axis + rowText
            };
            List<string> refs = new List<string>();
            refs.Add("Sheet." + Convert.ToInt32(target.ID, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
            try
            {
                string name = Convert.ToString(target.Name, CultureInfo.InvariantCulture) ?? "";
                if (!String.IsNullOrWhiteSpace(name)) refs.Add(name);
            }
            catch { }
            try
            {
                string nameU = Convert.ToString(target.NameU, CultureInfo.InvariantCulture) ?? "";
                if (!String.IsNullOrWhiteSpace(nameU)) refs.Add(nameU);
            }
            catch { }

            foreach (string targetRef in refs)
            {
                foreach (string suffix in suffixes)
                {
                    string direct = targetRef + suffix;
                    string quoted = "'" + targetRef + "'" + suffix;
                    if (value.IndexOf(direct, StringComparison.OrdinalIgnoreCase) >= 0 ||
                        value.IndexOf(quoted, StringComparison.OrdinalIgnoreCase) >= 0)
                        return true;
                }
            }
            return false;
        }

        private static bool IsGlueCorrect(dynamic page, Edge edge)
        {
            try
            {
                dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                dynamic target = page.Shapes.ItemFromID(edge.TargetId);
                string xName = edge.Endpoint == "begin" ? "BeginX" : "EndX";
                string yName = edge.Endpoint == "begin" ? "BeginY" : "EndY";
                string xFormula = Convert.ToString(source.CellsU(xName).FormulaU, CultureInfo.InvariantCulture) ?? "";
                string yFormula = Convert.ToString(source.CellsU(yName).FormulaU, CultureInfo.InvariantCulture) ?? "";

                // A valid 1-D Glue must bind BOTH coordinates to the same connection
                // point. This deliberately rejects VTD's half-Glue state where X is
                // numeric but Y still contains PAR(PNT(...)).
                return FormulaReferencesTarget(xFormula, target, edge.Row, "X") &&
                       FormulaReferencesTarget(yFormula, target, edge.Row, "Y");
            }
            catch { return false; }
        }

        private static void GlueAndVerify(dynamic page, Edge edge)
        {
            dynamic source = page.Shapes.ItemFromID(edge.SourceId);
            dynamic target = page.Shapes.ItemFromID(edge.TargetId);
            string sourceCellName = edge.Endpoint == "begin" ? "BeginX" : "EndX";
            string targetCellName = "Connections.X" + edge.Row.ToString(CultureInfo.InvariantCulture);
            source.CellsU(sourceCellName).GlueTo(target.CellsU(targetCellName));
            if (!IsGlueCorrect(page, edge))
                throw new InvalidOperationException(
                    String.Format(
                        CultureInfo.InvariantCulture,
                        "External GlueTo formula verification failed: source {0} {1}; target {2}/{3}",
                        edge.SourceId,
                        edge.Endpoint,
                        edge.TargetId,
                        edge.Row
                    )
                );
        }

        private static dynamic ResolveDocument(dynamic app, string documentName)
        {
            for (int index = 1; index <= (int)app.Documents.Count; index++)
            {
                dynamic candidate = app.Documents.Item(index);
                if (String.Equals(
                        Convert.ToString(candidate.Name, CultureInfo.InvariantCulture),
                        documentName,
                        StringComparison.OrdinalIgnoreCase))
                    return candidate;
            }
            throw new InvalidOperationException("Open Visio document not found: " + documentName);
        }

        private static dynamic ResolvePage(dynamic document, string pageName)
        {
            for (int index = 1; index <= (int)document.Pages.Count; index++)
            {
                dynamic candidate = document.Pages.Item(index);
                string name = Convert.ToString(candidate.Name, CultureInfo.InvariantCulture) ?? "";
                string nameU = Convert.ToString(candidate.NameU, CultureInfo.InvariantCulture) ?? "";
                if (String.Equals(name, pageName, StringComparison.OrdinalIgnoreCase) ||
                    String.Equals(nameU, pageName, StringComparison.OrdinalIgnoreCase))
                    return candidate;
            }
            throw new InvalidOperationException("Visio page not found: " + pageName);
        }

        private static double GetMm(dynamic shape, string cellName)
        {
            return Convert.ToDouble(
                shape.CellsU(cellName).ResultIU,
                CultureInfo.InvariantCulture
            ) * 25.4;
        }

        private static void SetMm(dynamic shape, string cellName, double valueMm)
        {
            shape.CellsU(cellName).FormulaU =
                valueMm.ToString("0.############", CultureInfo.InvariantCulture) + " mm";
        }

        private static bool CellExists(dynamic shape, string cellName)
        {
            try
            {
                dynamic cell = shape.CellsU(cellName);
                double ignored = Convert.ToDouble(cell.ResultIU, CultureInfo.InvariantCulture);
                return !Double.IsNaN(ignored);
            }
            catch { return false; }
        }

        private static string EndpointKey(int shapeId, string endpoint)
        {
            return shapeId.ToString(CultureInfo.InvariantCulture) + ":" +
                (endpoint ?? "").Trim().ToLowerInvariant();
        }

        private static void AddGeometryExpectation(
            dynamic shape,
            int shapeId,
            string cellName,
            Dictionary<string, GeometryExpectation> expectations)
        {
            dynamic cell = shape.CellsU(cellName);
            string key = shapeId.ToString(CultureInfo.InvariantCulture) + ":" + cellName;
            expectations[key] = new GeometryExpectation {
                ShapeId = shapeId,
                CellName = cellName,
                ExpectedMm = Convert.ToDouble(cell.ResultIU, CultureInfo.InvariantCulture) * 25.4,
                FormulaU = Convert.ToString(cell.FormulaU, CultureInfo.InvariantCulture) ?? ""
            };
        }

        private static void CapturePostMoveGeometry(
            dynamic page,
            MoveStep step,
            HashSet<string> glueOwnedEndpoints,
            Dictionary<string, GeometryExpectation> expectations)
        {
            foreach (int id in step.MemberIds)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                bool oneDimensional =
                    CellExists(shape, "BeginX") && CellExists(shape, "BeginY") &&
                    CellExists(shape, "EndX") && CellExists(shape, "EndY");
                if (oneDimensional)
                {
                    if (!glueOwnedEndpoints.Contains(EndpointKey(id, "begin")))
                    {
                        AddGeometryExpectation(shape, id, "BeginX", expectations);
                        AddGeometryExpectation(shape, id, "BeginY", expectations);
                    }
                    if (!glueOwnedEndpoints.Contains(EndpointKey(id, "end")))
                    {
                        AddGeometryExpectation(shape, id, "EndX", expectations);
                        AddGeometryExpectation(shape, id, "EndY", expectations);
                    }
                }
                else
                {
                    if (CellExists(shape, "PinX"))
                        AddGeometryExpectation(shape, id, "PinX", expectations);
                    if (CellExists(shape, "PinY"))
                        AddGeometryExpectation(shape, id, "PinY", expectations);
                }
            }
        }

        private static int RepairExpectedGeometry(
            dynamic page,
            Dictionary<string, GeometryExpectation> expectations,
            double toleranceMm)
        {
            int repaired = 0;
            foreach (GeometryExpectation expectation in expectations.Values)
            {
                dynamic shape = page.Shapes.ItemFromID(expectation.ShapeId);
                double actual = GetMm(shape, expectation.CellName);
                if (Math.Abs(actual - expectation.ExpectedMm) <= toleranceMm)
                    continue;
                shape.CellsU(expectation.CellName).FormulaU = expectation.FormulaU;
                double restored = GetMm(shape, expectation.CellName);
                if (Math.Abs(restored - expectation.ExpectedMm) > toleranceMm)
                    throw new InvalidOperationException(
                        String.Format(
                            CultureInfo.InvariantCulture,
                            "Geometry repair failed: shape {0} {1}; expected {2:0.###} mm, actual {3:0.###} mm",
                            expectation.ShapeId,
                            expectation.CellName,
                            expectation.ExpectedMm,
                            restored
                        )
                    );
                repaired++;
            }
            return repaired;
        }

        private static void VerifyExpectedGeometry(
            dynamic page,
            Dictionary<string, GeometryExpectation> expectations,
            double toleranceMm)
        {
            foreach (GeometryExpectation expectation in expectations.Values)
            {
                dynamic shape = page.Shapes.ItemFromID(expectation.ShapeId);
                double actual = GetMm(shape, expectation.CellName);
                if (Math.Abs(actual - expectation.ExpectedMm) > toleranceMm)
                    throw new InvalidOperationException(
                        String.Format(
                            CultureInfo.InvariantCulture,
                            "Geometry verification failed after stabilization: shape {0} {1}; expected {2:0.###} mm, actual {3:0.###} mm",
                            expectation.ShapeId,
                            expectation.CellName,
                            expectation.ExpectedMm,
                            actual
                        )
                    );
            }
        }

        private static void DetachEndpoint(dynamic shape, string endpoint)
        {
            string xName = endpoint == "begin" ? "BeginX" : "EndX";
            string yName = endpoint == "begin" ? "BeginY" : "EndY";
            double x = GetMm(shape, xName);
            double y = GetMm(shape, yName);
            SetMm(shape, xName, x);
            SetMm(shape, yName, y);
        }

        private static void SelectIds(dynamic app, dynamic page, IEnumerable<int> ids)
        {
            dynamic window = app.ActiveWindow;
            try { window.Page = page; }
            catch { try { page.Activate(); } catch { } }
            window.DeselectAll();
            int expected = 0;
            foreach (int id in ids)
            {
                window.Select(page.Shapes.ItemFromID(id), 2); // visSelect
                expected++;
            }
            if (Convert.ToInt32(window.Selection.Count, CultureInfo.InvariantCulture) != expected)
                throw new InvalidOperationException(
                    "Visio selected an unexpected number of transaction members"
                );
        }

        private static void ApplyMoveStep(
            dynamic page,
            dynamic preparedSelection,
            MoveStep step,
            HashSet<string> glueOwnedEndpoints,
            Dictionary<string, GeometryExpectation> geometryExpectations)
        {
            if (step.MemberIds.Count == 0)
                throw new InvalidOperationException("Move transaction has no member shapes");
            dynamic anchor = page.Shapes.ItemFromID(step.AnchorId);
            DetachEndpoint(anchor, step.Endpoint);

            Dictionary<int, double[]> before = new Dictionary<int, double[]>();
            foreach (int id in step.MemberIds)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                before[id] = new double[] { GetMm(shape, "PinX"), GetMm(shape, "PinY") };
            }

            if (preparedSelection == null ||
                Convert.ToInt32(preparedSelection.Count, CultureInfo.InvariantCulture) != step.MemberIds.Count)
                throw new InvalidOperationException(
                    "Prepared move selection does not match transaction members"
                );
            preparedSelection.Move(step.DxMm, step.DyMm, "mm");

            const double toleranceMm = 0.05;
            foreach (int id in step.MemberIds)
            {
                dynamic shape = page.Shapes.ItemFromID(id);
                double actualDx = GetMm(shape, "PinX") - before[id][0];
                double actualDy = GetMm(shape, "PinY") - before[id][1];
                if (Math.Abs(actualDx - step.DxMm) > toleranceMm ||
                    Math.Abs(actualDy - step.DyMm) > toleranceMm)
                    throw new InvalidOperationException(
                        String.Format(
                            CultureInfo.InvariantCulture,
                            "Move verification failed for shape {0}: expected ({1:0.###},{2:0.###}) mm, actual ({3:0.###},{4:0.###}) mm",
                            id,
                            step.DxMm,
                            step.DyMm,
                            actualDx,
                            actualDy
                        )
                    );
            }

            // Preserve Visio's own post-move formulas. Glue-owned endpoints are
            // excluded because their formulas are governed by EDGE expectations.
            CapturePostMoveGeometry(
                page, step, glueOwnedEndpoints, geometryExpectations
            );
        }

        [STAThread]
        private static int Main(string[] args)
        {
            string resultPath = args.Length > 1 ? args[args.Length - 1] : "";
            string tracePath = String.IsNullOrWhiteSpace(resultPath) ? "" : resultPath + ".trace";
            Trace(tracePath, "START apartment=" + Thread.CurrentThread.GetApartmentState().ToString());
            dynamic transactionApp = null;
            int transactionScope = 0;
            bool transactionCommitted = false;
            try
            {

                if (args.Length != 2)
                    throw new InvalidOperationException("Usage: EnergoLogic.TopologyRestoreHelper.exe <plan> <result>");

                string planPath = args[0];
                string documentName = "";
                string pageName = "";
                string scopeName = "";
                List<Edge> edges = new List<Edge>();
                List<MoveStep> moves = new List<MoveStep>();
                List<ExplicitDetach> explicitDetaches = new List<ExplicitDetach>();
                List<int> finalSelection = new List<int>();

                foreach (string raw in File.ReadAllLines(planPath, Encoding.UTF8))
                {
                    if (String.IsNullOrWhiteSpace(raw)) continue;
                    string[] parts = raw.Split('\t');
                    if (parts.Length == 2 && parts[0] == "DOC")
                        documentName = Decode(parts[1]);
                    else if (parts.Length == 2 && parts[0] == "PAGE")
                        pageName = Decode(parts[1]);
                    else if (parts.Length == 2 && parts[0] == "SCOPE")
                        scopeName = Decode(parts[1]);
                    else if (parts.Length == 7 && parts[0] == "MOVE")
                    {
                        MoveStep move = new MoveStep {
                            AnchorId = Int32.Parse(parts[1], CultureInfo.InvariantCulture),
                            Endpoint = parts[2],
                            DxMm = Double.Parse(parts[3], CultureInfo.InvariantCulture),
                            DyMm = Double.Parse(parts[4], CultureInfo.InvariantCulture)
                        };
                        foreach (string idText in parts[5].Split(','))
                        {
                            if (!String.IsNullOrWhiteSpace(idText))
                                move.MemberIds.Add(Int32.Parse(idText, CultureInfo.InvariantCulture));
                        }
                        // parts[6] is reserved for a stable cell label / future audit metadata.
                        moves.Add(move);
                    }
                    else if (parts.Length == 3 && parts[0] == "DETACH")
                    {
                        string explicitEndpoint = parts[2].Trim().ToLowerInvariant();
                        if (explicitEndpoint != "begin" && explicitEndpoint != "end")
                            throw new InvalidOperationException("DETACH endpoint must be begin or end");
                        explicitDetaches.Add(new ExplicitDetach {
                            ShapeId = Int32.Parse(parts[1], CultureInfo.InvariantCulture),
                            Endpoint = explicitEndpoint
                        });
                    }
                    else if (parts.Length == 2 && parts[0] == "SELECT")
                    {
                        foreach (string idText in parts[1].Split(','))
                        {
                            if (!String.IsNullOrWhiteSpace(idText))
                                finalSelection.Add(Int32.Parse(idText, CultureInfo.InvariantCulture));
                        }
                    }
                    else if (parts.Length == 5 && parts[0] == "EDGE")
                    {
                        edges.Add(new Edge {
                            SourceId = Int32.Parse(parts[1], CultureInfo.InvariantCulture),
                            Endpoint = parts[2],
                            TargetId = Int32.Parse(parts[3], CultureInfo.InvariantCulture),
                            Row = Int32.Parse(parts[4], CultureInfo.InvariantCulture)
                        });
                    }
                }

                if (String.IsNullOrWhiteSpace(documentName) || String.IsNullOrWhiteSpace(pageName))
                    throw new InvalidOperationException("Topology plan is missing document/page identity");
                dynamic app = Marshal.GetActiveObject("Visio.Application");
                Trace(tracePath, "GOT_ACTIVE_OBJECT");
                dynamic document = ResolveDocument(app, documentName);
                dynamic page = ResolvePage(document, pageName);

                HashSet<string> glueOwnedEndpoints = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase
                );
                foreach (Edge edge in edges)
                    glueOwnedEndpoints.Add(EndpointKey(edge.SourceId, edge.Endpoint));
                // If one moved 1-D source has BOTH endpoints represented in the expected
                // topology, detach its managed endpoints explicitly before Selection.Move.
                // Visio may otherwise break one side implicitly; that hidden break is not
                // reliably restored by a single native Undo. Singly-managed endpoints are
                // intentionally left untouched because VTD can use nonstandard formulas.
                HashSet<string> moveAnchorEndpoints = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase
                );
                HashSet<int> movedMemberIds = new HashSet<int>();
                foreach (MoveStep move in moves)
                {
                    moveAnchorEndpoints.Add(EndpointKey(move.AnchorId, move.Endpoint));
                    foreach (int memberId in move.MemberIds)
                        movedMemberIds.Add(memberId);
                }

                HashSet<string> explicitDetachKeys = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase
                );
                foreach (ExplicitDetach explicitDetach in explicitDetaches)
                    explicitDetachKeys.Add(
                        EndpointKey(explicitDetach.ShapeId, explicitDetach.Endpoint)
                    );

                Dictionary<int, HashSet<string>> managedEndpointsBySource =
                    new Dictionary<int, HashSet<string>>();
                foreach (Edge edge in edges)
                {
                    HashSet<string> managedEndpoints;
                    if (!managedEndpointsBySource.TryGetValue(edge.SourceId, out managedEndpoints))
                    {
                        managedEndpoints = new HashSet<string>(
                            StringComparer.OrdinalIgnoreCase
                        );
                        managedEndpointsBySource[edge.SourceId] = managedEndpoints;
                    }
                    managedEndpoints.Add((edge.Endpoint ?? "").Trim().ToLowerInvariant());
                }

                int autoDetachCount = 0;
                foreach (KeyValuePair<int, HashSet<string>> item in managedEndpointsBySource)
                {
                    if (!movedMemberIds.Contains(item.Key) ||
                        !item.Value.Contains("begin") ||
                        !item.Value.Contains("end"))
                        continue;

                    foreach (string endpoint in new string[] { "begin", "end" })
                    {
                        string key = EndpointKey(item.Key, endpoint);
                        // ApplyMoveStep already owns the anchor endpoint detach.
                        if (moveAnchorEndpoints.Contains(key) || explicitDetachKeys.Contains(key))
                            continue;
                        explicitDetaches.Add(new ExplicitDetach {
                            ShapeId = item.Key,
                            Endpoint = endpoint
                        });
                        explicitDetachKeys.Add(key);
                        autoDetachCount++;
                    }
                }
                if (autoDetachCount > 0)
                    Trace(
                        tracePath,
                        "AUTO_DETACH_DOUBLE_ENDED count=" +
                        autoDetachCount.ToString(CultureInfo.InvariantCulture)
                    );

                Dictionary<string, GeometryExpectation> geometryExpectations =
                    new Dictionary<string, GeometryExpectation>(StringComparer.OrdinalIgnoreCase);

                // Build independent, off-screen Selection objects BEFORE opening the
                // native UndoScope. Selection.Select changes only the Selection object
                // in memory and does not mutate the window selection. This lets both
                // single Move and multi-step Distribute use Selection.Move without any
                // UI-selection change while the compound scope is open.
                List<dynamic> preparedMoveSelections = new List<dynamic>();
                foreach (MoveStep move in moves)
                {
                    dynamic prepared = page.CreateSelection(0, 0x100); // visSelTypeEmpty, visSelModeSkipSuper
                    foreach (int memberId in move.MemberIds)
                        prepared.Select(page.Shapes.ItemFromID(memberId), 2); // visSelect
                    if (Convert.ToInt32(prepared.Count, CultureInfo.InvariantCulture) != move.MemberIds.Count)
                        throw new InvalidOperationException(
                            "Could not prepare an off-screen selection for move transaction"
                        );
                    preparedMoveSelections.Add(prepared);
                }
                if (moves.Count > 0)
                    Trace(tracePath, "MOVE_SELECTIONS_PREPARED count=" + moves.Count.ToString(CultureInfo.InvariantCulture));

                if (moves.Count > 0)
                {
                    if (String.IsNullOrWhiteSpace(scopeName))
                        scopeName = "EnergoLogic: compound transaction";
                    transactionApp = app;
                    transactionScope = Convert.ToInt32(
                        app.BeginUndoScope(scopeName),
                        CultureInfo.InvariantCulture
                    );
                    Trace(tracePath, "SCOPE_BEGIN owner=application id=" + transactionScope.ToString(CultureInfo.InvariantCulture));
                    foreach (ExplicitDetach explicitDetach in explicitDetaches)
                        DetachEndpoint(
                            page.Shapes.ItemFromID(explicitDetach.ShapeId),
                            explicitDetach.Endpoint
                        );
                    if (explicitDetaches.Count > 0)
                        Trace(tracePath, "EXPLICIT_DETACHES_APPLIED count=" + explicitDetaches.Count.ToString(CultureInfo.InvariantCulture));
                    for (int moveIndex = 0; moveIndex < moves.Count; moveIndex++)
                        ApplyMoveStep(
                            page, preparedMoveSelections[moveIndex], moves[moveIndex],
                            glueOwnedEndpoints, geometryExpectations
                        );
                    Trace(tracePath, "MOVES_APPLIED count=" + moves.Count.ToString(CultureInfo.InvariantCulture));
                }

                // IMPORTANT: no window selection changes are allowed while the compound
                // native UndoScope is open. All move selections were created off-screen
                // before BeginUndoScope; final UI selection remains outside the scope.

                int repaired = 0;
                int geometryRepaired = 0;
                int verified = edges.Count;
                int cleanRounds = 0;
                int rounds = 0;
                const int requiredCleanRounds = 8;
                const int maxRounds = 20;
                const int pollMilliseconds = 250;

                const double geometryToleranceMm = 0.05;
                for (rounds = 1; rounds <= maxRounds; rounds++)
                {
                    int repairedThisRound = 0;
                    int geometryRepairedThisRound = RepairExpectedGeometry(
                        page, geometryExpectations, geometryToleranceMm
                    );
                    geometryRepaired += geometryRepairedThisRound;

                    foreach (Edge edge in edges)
                    {
                        try
                        {
                            if (!IsGlueCorrect(page, edge))
                            {
                                GlueAndVerify(page, edge);
                                repaired++;
                                repairedThisRound++;
                            }
                        }
                        catch (Exception edgeError)
                        {
                            throw new InvalidOperationException(
                                String.Format(CultureInfo.InvariantCulture,
                                    "External Glue repair failed: source {0} {1}; target {2}/{3}",
                                    edge.SourceId, edge.Endpoint, edge.TargetId, edge.Row),
                                edgeError);
                        }
                    }

                    // Glue/VTD may rewrite free 1-D endpoints as a side effect.
                    // Re-assert Visio's own post-move formulas before verification.
                    int geometryAfterGlue = RepairExpectedGeometry(
                        page, geometryExpectations, geometryToleranceMm
                    );
                    geometryRepairedThisRound += geometryAfterGlue;
                    geometryRepaired += geometryAfterGlue;

                    // Verify the complete expected topology AND final geometry after
                    // all repairs in this round. Formula-pair verification rejects
                    // VTD half-Glue while geometry verification rejects stretched
                    // or partially reverted 1-D members.
                    foreach (Edge edge in edges)
                    {
                        if (!IsGlueCorrect(page, edge))
                            throw new InvalidOperationException(
                                String.Format(
                                    CultureInfo.InvariantCulture,
                                    "External topology verification failed after repair: source {0} {1}; target {2}/{3}",
                                    edge.SourceId,
                                    edge.Endpoint,
                                    edge.TargetId,
                                    edge.Row
                                )
                            );
                    }

                    VerifyExpectedGeometry(
                        page, geometryExpectations, geometryToleranceMm
                    );

                    // MOVE transactions have a stronger live proof than a delayed
                    // stability window: detach -> Selection.Move -> all required Glue
                    // -> immediate full topology/geometry verification inside one
                    // native UndoScope remains stable after commit. Keeping that scope
                    // open while sleeping lets VTD enqueue/execute extra solution work
                    // and was observed to corrupt a free 1-D endpoint. Therefore a
                    // MOVE commits immediately after one complete verified repair pass.
                    if (moves.Count > 0)
                    {
                        cleanRounds = 1;
                        break;
                    }

                    if (repairedThisRound == 0 && geometryRepairedThisRound == 0)
                        cleanRounds++;
                    else
                        cleanRounds = 0;

                    if (cleanRounds >= requiredCleanRounds)
                        break;

                    // Topology-only/replacement work still needs the bounded delayed
                    // VTD stabilization window because those operations can schedule
                    // asynchronous ShapeSheet rewrites after the immediate repair.
                    Thread.Sleep(pollMilliseconds);
                }

                int requiredForMode = moves.Count > 0 ? 1 : requiredCleanRounds;
                if (cleanRounds < requiredForMode)
                    throw new InvalidOperationException(
                        "External topology did not stabilize: clean=" +
                        cleanRounds.ToString(CultureInfo.InvariantCulture) +
                        "/" + requiredForMode.ToString(CultureInfo.InvariantCulture) +
                        "; rounds=" + rounds.ToString(CultureInfo.InvariantCulture)
                    );

                if (transactionScope > 0)
                {
                    Trace(tracePath, "SCOPE_COMMIT_BEGIN");
                    app.EndUndoScope(transactionScope, true);
                    transactionCommitted = true;
                    transactionScope = 0;
                    Trace(tracePath, "SCOPE_COMMIT_END");
                }

                // V362 safety rule: a short-lived external COM owner must make no
                // UI/ShapeSheet calls after committing a MOVE scope. The preceding
                // ApplyMoveStep already leaves the moved cell selected for a single
                // move. Multi-move/distribute selection restoration is deliberately
                // deferred until we have a safe in-process UI handoff.
                if (moves.Count == 0 && finalSelection.Count > 0)
                    SelectIds(app, page, finalSelection);
                Trace(tracePath, moves.Count > 0 ? "POST_COMMIT_VISIO_CALLS_SKIPPED" : "POST_COMMIT_SELECTION_DONE");

                File.WriteAllText(
                    resultPath,
                    "PASS\t" +
                    repaired.ToString(CultureInfo.InvariantCulture) + "\t" +
                    verified.ToString(CultureInfo.InvariantCulture) + "\t" +
                    rounds.ToString(CultureInfo.InvariantCulture) + "\t" +
                    cleanRounds.ToString(CultureInfo.InvariantCulture) + "\t" +
                    (moves.Count > 0 ? "owned-scope" : "topology-only") + "\t" +
                    geometryRepaired.ToString(CultureInfo.InvariantCulture),
                    Encoding.UTF8
                );
                Trace(tracePath, "RESULT_WRITTEN PASS");
                Trace(tracePath, "RETURN 0");
                return 0;
            }
            catch (Exception ex)
            {
                bool rolledBack = false;
                if (!transactionCommitted && transactionScope > 0 && transactionApp != null)
                {
                    try
                    {
                        transactionApp.EndUndoScope(transactionScope, false);
                        rolledBack = true;
                    }
                    catch { }
                }
                try
                {
                    if (!String.IsNullOrWhiteSpace(resultPath))
                        File.WriteAllText(
                            resultPath,
                            (rolledBack ? "ERROR_ROLLED_BACK\t" : "ERROR\t") + ex.ToString(),
                            Encoding.UTF8
                        );
                }
                catch { }
                Trace(tracePath, "RETURN 1 " + ex.GetType().FullName);
                return 1;
            }
        }
    }
}
