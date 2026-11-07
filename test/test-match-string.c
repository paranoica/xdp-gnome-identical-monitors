#include "config.h"

#include <gio/gio.h>

#include "displaystatetracker.h"

#define LG_PAIR_LEFT \
  "{\"connector\": \"DVI-D-1\", \"vendor\": \"GSM\", \"product\": \"LG FULL HD\"," \
  " \"serial\": \"0x01010101\", \"x\": 0, \"y\": 0}"
#define LG_PAIR_RIGHT \
  "{\"connector\": \"HDMI-1\", \"vendor\": \"GSM\", \"product\": \"LG FULL HD\"," \
  " \"serial\": \"0x01010101\", \"x\": 1920, \"y\": 0}"
#define DELL \
  "{\"connector\": \"DP-1\", \"vendor\": \"DEL\", \"product\": \"DELL U2414H\"," \
  " \"serial\": \"0x12345678\", \"x\": 3840, \"y\": 0}"

static DisplayStateTracker *tracker;
static GMainLoop *loop;

static void
on_monitors_changed (DisplayStateTracker *self,
                     gpointer             user_data)
{
  g_main_loop_quit (loop);
}

static gboolean
on_timeout (gpointer user_data)
{
  g_error ("Timed out waiting for monitors-changed");
  return G_SOURCE_REMOVE;
}

static void
wait_for_monitors_changed (void)
{
  guint timeout_id = g_timeout_add_seconds (5, on_timeout, NULL);

  g_main_loop_run (loop);
  g_source_remove (timeout_id);
}

static GList *
all_monitors (void)
{
  GList *monitors = NULL;
  GList *l;

  for (l = display_state_tracker_get_logical_monitors (tracker); l; l = l->next)
    monitors = g_list_concat (monitors,
                              g_list_copy (logical_monitor_get_monitors (l->data)));

  return monitors;
}

/* mock_mutter puts the layout serial into every display name */
static gboolean
tracker_has_layout (guint32  serial,
                    gboolean empty)
{
  g_autoptr(GList) monitors = all_monitors ();
  g_autofree char *suffix = g_strdup_printf ("(layout %u)", serial);

  if (empty)
    return monitors == NULL;

  return monitors != NULL &&
         g_str_has_suffix (monitor_get_display_name (monitors->data), suffix);
}

static void
set_layout (const char *layout_json)
{
  g_autoptr(GDBusConnection) bus = NULL;
  g_autoptr(GVariant) reply = NULL;
  g_autoptr(GError) error = NULL;
  guint32 serial;

  bus = g_bus_get_sync (G_BUS_TYPE_SESSION, NULL, &error);
  g_assert_no_error (error);

  reply = g_dbus_connection_call_sync (bus,
                                       "test.MockMutter",
                                       "/test/MockMutter",
                                       "test.MockMutter.Control",
                                       "SetLayout",
                                       g_variant_new ("(s)", layout_json),
                                       G_VARIANT_TYPE ("(u)"),
                                       G_DBUS_CALL_FLAGS_NONE,
                                       -1, NULL, &error);
  g_assert_no_error (error);
  g_variant_get (reply, "(u)", &serial);

  while (!tracker_has_layout (serial, g_strcmp0 (layout_json, "[]") == 0))
    wait_for_monitors_changed ();
}

static const char *
match_string_of (const char *connector)
{
  g_autoptr(GList) monitors = all_monitors ();
  GList *l;

  for (l = monitors; l; l = l->next)
    {
      if (g_strcmp0 (monitor_get_connector (l->data), connector) == 0)
        return monitor_get_match_string (l->data);
    }

  g_error ("No monitor on connector %s", connector);
  return NULL;
}

static void
assert_match_strings_unique (void)
{
  g_autoptr(GList) monitors = all_monitors ();
  GList *l;

  for (l = monitors; l; l = l->next)
    {
      GList *k;

      for (k = l->next; k; k = k->next)
        g_assert_cmpstr (monitor_get_match_string (l->data), !=,
                         monitor_get_match_string (k->data));
    }
}

static void
test_identical_pair (void)
{
  set_layout ("[" LG_PAIR_LEFT ", " LG_PAIR_RIGHT "]");

  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "DVI-D-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");
  assert_match_strings_unique ();
}

static void
test_identical_pair_reversed_order (void)
{
  set_layout ("[" LG_PAIR_RIGHT ", " LG_PAIR_LEFT "]");

  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "DVI-D-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");
}

static void
test_distinct_monitors_unchanged (void)
{
  set_layout ("[" LG_PAIR_LEFT ", " DELL "]");

  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("DP-1"), ==, "DEL:DELL U2414H:0x12345678");
}

static void
test_identical_pair_plus_other (void)
{
  set_layout ("[" DELL ", " LG_PAIR_LEFT ", " LG_PAIR_RIGHT "]");

  g_assert_cmpstr (match_string_of ("DP-1"), ==, "DEL:DELL U2414H:0x12345678");
  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "DVI-D-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");
  assert_match_strings_unique ();
}

static void
test_three_identical (void)
{
  set_layout ("[" LG_PAIR_LEFT ", " LG_PAIR_RIGHT ", "
              "{\"connector\": \"DP-2\", \"vendor\": \"GSM\", \"product\": \"LG FULL HD\","
              " \"serial\": \"0x01010101\", \"x\": 3840, \"y\": 0}"
              "]");

  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "DVI-D-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("DP-2"), ==, "DP-2:GSM:LG FULL HD:0x01010101");
  assert_match_strings_unique ();
}

static void
test_two_pairs_and_unique (void)
{
  set_layout ("[" LG_PAIR_LEFT ", " LG_PAIR_RIGHT ", " DELL ", "
              "{\"connector\": \"DP-2\", \"vendor\": \"DEL\", \"product\": \"DELL U2414H\","
              " \"serial\": \"0x12345678\", \"x\": 5760, \"y\": 0}, "
              "{\"connector\": \"DP-3\", \"vendor\": \"SAM\", \"product\": \"S24F350\","
              " \"serial\": \"0x4e584d30\", \"x\": 7680, \"y\": 0}"
              "]");

  g_assert_cmpstr (match_string_of ("DVI-D-1"), ==, "DVI-D-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");
  g_assert_cmpstr (match_string_of ("DP-1"), ==, "DP-1:DEL:DELL U2414H:0x12345678");
  g_assert_cmpstr (match_string_of ("DP-2"), ==, "DP-2:DEL:DELL U2414H:0x12345678");
  g_assert_cmpstr (match_string_of ("DP-3"), ==, "SAM:S24F350:0x4e584d30");
  assert_match_strings_unique ();
}

static void
test_builtin_and_external_identical (void)
{
  set_layout ("["
              "{\"connector\": \"eDP-1\", \"vendor\": \"BOE\", \"product\": \"0x0abc\","
              " \"serial\": \"0x00000000\", \"x\": 0, \"y\": 0, \"builtin\": true}, "
              "{\"connector\": \"HDMI-1\", \"vendor\": \"BOE\", \"product\": \"0x0abc\","
              " \"serial\": \"0x00000000\", \"x\": 1920, \"y\": 0}"
              "]");

  g_assert_cmpstr (match_string_of ("eDP-1"), ==, "eDP-1:BOE:0x0abc:0x00000000");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:BOE:0x0abc:0x00000000");
}

static void
test_unknown_edid_uses_connector (void)
{
  set_layout ("["
              "{\"connector\": \"Virtual-1\", \"vendor\": \"unknown\", \"product\": \"unknown\","
              " \"serial\": \"unknown\", \"x\": 0, \"y\": 0}, "
              "{\"connector\": \"Virtual-2\", \"vendor\": \"unknown\", \"product\": \"unknown\","
              " \"serial\": \"unknown\", \"x\": 1920, \"y\": 0}"
              "]");

  g_assert_cmpstr (match_string_of ("Virtual-1"), ==, "Virtual-1");
  g_assert_cmpstr (match_string_of ("Virtual-2"), ==, "Virtual-2");
}

static void
test_single_monitor_unchanged (void)
{
  set_layout ("[" LG_PAIR_RIGHT "]");

  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "GSM:LG FULL HD:0x01010101");
}

static void
test_unplugging_twin_restores_plain_string (void)
{
  set_layout ("[" LG_PAIR_LEFT ", " LG_PAIR_RIGHT "]");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "HDMI-1:GSM:LG FULL HD:0x01010101");

  set_layout ("[" LG_PAIR_RIGHT "]");
  g_assert_cmpstr (match_string_of ("HDMI-1"), ==, "GSM:LG FULL HD:0x01010101");
}

static void
test_no_monitors (void)
{
  g_autoptr(GList) monitors = NULL;

  set_layout ("[]");

  monitors = all_monitors ();
  g_assert_null (monitors);
}

int
main (int    argc,
      char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_set_nonfatal_assertions ();

  loop = g_main_loop_new (NULL, FALSE);
  tracker = display_state_tracker_get ();
  g_signal_connect (tracker, "monitors-changed",
                    G_CALLBACK (on_monitors_changed), NULL);
  set_layout ("[]");

  g_test_add_func ("/match-string/identical-pair", test_identical_pair);
  g_test_add_func ("/match-string/identical-pair-reversed-order",
                   test_identical_pair_reversed_order);
  g_test_add_func ("/match-string/distinct-monitors-unchanged",
                   test_distinct_monitors_unchanged);
  g_test_add_func ("/match-string/identical-pair-plus-other",
                   test_identical_pair_plus_other);
  g_test_add_func ("/match-string/three-identical", test_three_identical);
  g_test_add_func ("/match-string/two-pairs-and-unique", test_two_pairs_and_unique);
  g_test_add_func ("/match-string/builtin-and-external-identical",
                   test_builtin_and_external_identical);
  g_test_add_func ("/match-string/unknown-edid-uses-connector",
                   test_unknown_edid_uses_connector);
  g_test_add_func ("/match-string/single-monitor-unchanged",
                   test_single_monitor_unchanged);
  g_test_add_func ("/match-string/unplugging-twin-restores-plain-string",
                   test_unplugging_twin_restores_plain_string);
  g_test_add_func ("/match-string/no-monitors", test_no_monitors);

  return g_test_run ();
}
