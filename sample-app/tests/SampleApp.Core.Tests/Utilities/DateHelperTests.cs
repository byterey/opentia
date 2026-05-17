using FluentAssertions;
using SampleApp.Core.Utilities;

namespace SampleApp.Core.Tests.Utilities;

public class DateHelperTests
{
    [Theory]
    [InlineData(DayOfWeek.Saturday, true)]
    [InlineData(DayOfWeek.Sunday,   true)]
    [InlineData(DayOfWeek.Monday,   false)]
    [InlineData(DayOfWeek.Friday,   false)]
    public void IsWeekend_CorrectPerDay(DayOfWeek day, bool expected)
    {
        // Find the next occurrence of that day of week
        var date = DateTime.Today;
        while (date.DayOfWeek != day) date = date.AddDays(1);
        DateHelper.IsWeekend(date).Should().Be(expected);
    }

    [Fact]
    public void AddBusinessDays_SkipsWeekends()
    {
        // Start on a Friday; +1 business day should land on Monday
        var friday = GetNextWeekday(DayOfWeek.Friday);
        var result = DateHelper.AddBusinessDays(friday, 1);
        result.DayOfWeek.Should().Be(DayOfWeek.Monday);
    }

    [Fact]
    public void AddBusinessDays_ZeroDays_ReturnsSameDate()
    {
        var date = new DateTime(2024, 1, 15); // Monday
        DateHelper.AddBusinessDays(date, 0).Should().Be(date);
    }

    [Fact]
    public void CountBusinessDaysBetween_EndBeforeStart_Throws()
    {
        var start = new DateTime(2024, 1, 10);
        var end   = new DateTime(2024, 1, 5);
        Assert.Throws<ArgumentException>(() => DateHelper.CountBusinessDaysBetween(start, end));
    }

    [Fact]
    public void CountBusinessDaysBetween_SameDate_ReturnsZero()
    {
        var date = new DateTime(2024, 1, 15);
        DateHelper.CountBusinessDaysBetween(date, date).Should().Be(0);
    }

    [Fact]
    public void CountBusinessDaysBetween_OneWeek_ReturnsFive()
    {
        var monday = GetNextWeekday(DayOfWeek.Monday);
        var nextMonday = monday.AddDays(7);
        DateHelper.CountBusinessDaysBetween(monday, nextMonday).Should().Be(5);
    }

    [Fact]
    public void GetAgeInYears_CalculatesCorrectly()
    {
        var birthDate = DateTime.Today.AddYears(-30);
        DateHelper.GetAgeInYears(birthDate).Should().Be(30);
    }

    private static DateTime GetNextWeekday(DayOfWeek day)
    {
        var date = DateTime.Today;
        while (date.DayOfWeek != day) date = date.AddDays(1);
        return date;
    }
}
