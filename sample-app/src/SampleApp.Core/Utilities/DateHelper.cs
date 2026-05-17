namespace SampleApp.Core.Utilities;

public static class DateHelper
{
    public static bool IsWeekend(DateTime date) =>
        date.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday;

    public static bool IsBusinessDay(DateTime date) => !IsWeekend(date);

    public static DateTime AddBusinessDays(DateTime date, int days)
    {
        var direction = days >= 0 ? 1 : -1;
        var remaining = Math.Abs(days);
        var current = date;
        while (remaining > 0)
        {
            current = current.AddDays(direction);
            if (IsBusinessDay(current)) remaining--;
        }
        return current;
    }

    public static int CountBusinessDaysBetween(DateTime start, DateTime end)
    {
        if (end < start) throw new ArgumentException("end must be after start");
        var count = 0;
        var current = start.Date;
        while (current < end.Date)
        {
            current = current.AddDays(1);
            if (IsBusinessDay(current)) count++;
        }
        return count;
    }

    public static string ToRelativeString(DateTime date)
    {
        var diff = DateTime.UtcNow - date;
        return diff.TotalDays switch
        {
            < 1  => "Today",
            < 2  => "Yesterday",
            < 7  => $"{(int)diff.TotalDays} days ago",
            < 30 => $"{(int)(diff.TotalDays / 7)} week(s) ago",
            _    => date.ToString("yyyy-MM-dd"),
        };
    }

    public static int GetAgeInYears(DateTime birthDate)
    {
        var today = DateTime.Today;
        var age = today.Year - birthDate.Year;
        if (birthDate.Date > today.AddYears(-age)) age--;
        return age;
    }
}
